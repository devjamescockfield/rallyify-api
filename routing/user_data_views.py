import uuid

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from routing.authentication import SupabaseJWTAuthentication
from routing.economy import EconomyCalculationError
from routing.models import CompletedDrive, FuelEconomyRecord, VehicleProfile
from routing.throttles import (
    UserDataIPThrottle,
    UserDataUserBurstThrottle,
    UserDataUserDailyThrottle,
)
from routing.user_data_serializers import (
    CompletedDriveSerializer,
    FuelEconomyInputSerializer,
    VehicleProfileSerializer,
    serialize_fuel_record,
)
from routing.user_data_services import (
    DriveIdempotencyConflict,
    create_completed_drive,
    set_default_vehicle,
    update_completed_drive,
    upsert_fuel_record,
)


class UserDataAPIView(APIView):
    authentication_classes = [SupabaseJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [
        UserDataUserBurstThrottle,
        UserDataUserDailyThrottle,
        UserDataIPThrottle,
    ]

    def owner_id(self):
        return uuid.UUID(self.request.user.subject)


class VehicleCollectionView(UserDataAPIView):
    def get(self, request):
        vehicles = VehicleProfile.objects.filter(owner_id=self.owner_id())
        return Response(VehicleProfileSerializer(vehicles, many=True).data)

    def post(self, request):
        owner_id = self.owner_id()
        if (
            VehicleProfile.objects.filter(owner_id=owner_id).count()
            >= settings.USER_DATA_MAX_VEHICLES
        ):
            return api_error(
                "VEHICLE_LIMIT_REACHED",
                "The vehicle profile limit has been reached.",
                status.HTTP_409_CONFLICT,
            )
        serializer = VehicleProfileSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error(serializer.errors)
        make_default = serializer.validated_data.pop("is_default", False)
        with transaction.atomic():
            vehicle = serializer.save(owner_id=owner_id, is_default=False)
            if make_default:
                set_default_vehicle(vehicle)
        return Response(
            VehicleProfileSerializer(vehicle).data,
            status=status.HTTP_201_CREATED,
        )


class VehicleDetailView(UserDataAPIView):
    def get_vehicle(self, vehicle_id):
        return VehicleProfile.objects.filter(
            id=vehicle_id,
            owner_id=self.owner_id(),
        ).first()

    def get(self, request, vehicle_id):
        vehicle = self.get_vehicle(vehicle_id)
        if not vehicle:
            return not_found("VEHICLE_NOT_FOUND", "Vehicle was not found.")
        return Response(VehicleProfileSerializer(vehicle).data)

    def patch(self, request, vehicle_id):
        vehicle = self.get_vehicle(vehicle_id)
        if not vehicle:
            return not_found("VEHICLE_NOT_FOUND", "Vehicle was not found.")
        serializer = VehicleProfileSerializer(
            vehicle,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return validation_error(serializer.errors)
        make_default = serializer.validated_data.pop("is_default", None)
        with transaction.atomic():
            vehicle = serializer.save()
            if make_default is True:
                set_default_vehicle(vehicle)
            elif make_default is False and vehicle.is_default:
                vehicle.is_default = False
                vehicle.save(update_fields=["is_default", "updated_at"])
        return Response(VehicleProfileSerializer(vehicle).data)

    def delete(self, request, vehicle_id):
        vehicle = self.get_vehicle(vehicle_id)
        if not vehicle:
            return not_found("VEHICLE_NOT_FOUND", "Vehicle was not found.")
        vehicle.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SetDefaultVehicleView(UserDataAPIView):
    def post(self, request, vehicle_id):
        vehicle = VehicleProfile.objects.filter(
            id=vehicle_id,
            owner_id=self.owner_id(),
        ).first()
        if not vehicle:
            return not_found("VEHICLE_NOT_FOUND", "Vehicle was not found.")
        set_default_vehicle(vehicle)
        return Response(VehicleProfileSerializer(vehicle).data)


class DriveHistoryPagination(PageNumberPagination):
    page_size = settings.DRIVE_HISTORY_DEFAULT_PAGE_SIZE
    page_size_query_param = "pageSize"
    max_page_size = settings.DRIVE_HISTORY_MAX_PAGE_SIZE


class DriveCollectionView(UserDataAPIView):
    def get(self, request):
        drives = CompletedDrive.objects.filter(
            owner_id=self.owner_id()
        ).select_related("vehicle")
        paginator = DriveHistoryPagination()
        page = paginator.paginate_queryset(drives, request, view=self)
        data = [serialize_drive(drive) for drive in page]
        return paginator.get_paginated_response(data)

    def post(self, request):
        owner_id = self.owner_id()
        serializer = CompletedDriveSerializer(
            data=request.data,
            context={"owner_id": owner_id},
        )
        if not serializer.is_valid():
            return validation_error(serializer.errors)
        try:
            drive, duplicate = create_completed_drive(
                owner_id=owner_id,
                validated_data=serializer.validated_data,
            )
        except DriveIdempotencyConflict:
            return api_error(
                "COMPLETION_ID_REUSED",
                "completionId was already used with different drive data.",
                status.HTTP_409_CONFLICT,
            )
        body = serialize_drive(drive)
        body["duplicate"] = duplicate
        return Response(
            body,
            status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED,
        )


class DriveDetailView(UserDataAPIView):
    def get_drive(self, drive_id):
        return CompletedDrive.objects.filter(
            id=drive_id,
            owner_id=self.owner_id(),
        ).select_related("vehicle").first()

    def get(self, request, drive_id):
        drive = self.get_drive(drive_id)
        if not drive:
            return not_found("DRIVE_NOT_FOUND", "Completed drive was not found.")
        return Response(serialize_drive(drive))

    def patch(self, request, drive_id):
        drive = self.get_drive(drive_id)
        if not drive:
            return not_found("DRIVE_NOT_FOUND", "Completed drive was not found.")
        if "completionId" in request.data:
            return api_error(
                "IMMUTABLE_FIELD",
                "completionId cannot be changed.",
                status.HTTP_400_BAD_REQUEST,
            )
        serializer = CompletedDriveSerializer(
            drive,
            data=request.data,
            partial=True,
            context={"owner_id": self.owner_id()},
        )
        if not serializer.is_valid():
            return validation_error(serializer.errors)
        drive = update_completed_drive(drive, serializer.validated_data)
        return Response(serialize_drive(drive))

    def delete(self, request, drive_id):
        drive = self.get_drive(drive_id)
        if not drive:
            return not_found("DRIVE_NOT_FOUND", "Completed drive was not found.")
        drive.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DriveFuelView(UserDataAPIView):
    def get_drive(self, drive_id):
        return CompletedDrive.objects.filter(
            id=drive_id,
            owner_id=self.owner_id(),
        ).select_related("vehicle").first()

    def put(self, request, drive_id):
        drive = self.get_drive(drive_id)
        if not drive:
            return not_found("DRIVE_NOT_FOUND", "Completed drive was not found.")
        serializer = FuelEconomyInputSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error(serializer.errors)
        try:
            record = upsert_fuel_record(
                drive=drive,
                validated_data=serializer.validated_data,
            )
        except EconomyCalculationError as exc:
            return api_error(
                "INVALID_ECONOMY_INPUT",
                str(exc),
                status.HTTP_400_BAD_REQUEST,
            )
        return Response(serialize_fuel_record(record))

    def delete(self, request, drive_id):
        drive = self.get_drive(drive_id)
        if not drive:
            return not_found("DRIVE_NOT_FOUND", "Completed drive was not found.")
        FuelEconomyRecord.objects.filter(completed_drive=drive).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def serialize_drive(drive: CompletedDrive) -> dict:
    data = CompletedDriveSerializer(
        drive,
        context={"owner_id": drive.owner_id},
    ).data
    try:
        fuel = drive.fuel_record
    except FuelEconomyRecord.DoesNotExist:
        fuel = None
    data["fuel"] = serialize_fuel_record(fuel) if fuel else None
    return data


def validation_error(details):
    return Response(
        {
            "error": "Request validation failed.",
            "code": "VALIDATION_ERROR",
            "details": details,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def not_found(code, message):
    return api_error(code, message, status.HTTP_404_NOT_FOUND)


def api_error(code, message, status_code):
    return Response(
        {"error": message, "code": code},
        status=status_code,
    )
