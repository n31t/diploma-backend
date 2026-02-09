"""
User limits and detection history API endpoints.
"""

from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, HTTPException, status, Depends, Query

from src.api.v1.schemas.limits import (
    UserLimitsResponse,
    DetectionHistoryResponse,
    DetectionHistoryItem,
    UserStatsResponse
)
from src.core.logging import get_logger
from src.dtos import AuthenticatedUserDTO
from src.repositories.ai_detection_repository import AIDetectionRepository
from src.services.ai_detection_service import AIDetectionService
from src.services.shared.auth_helpers import get_authenticated_user_dependency

logger = get_logger(__name__)

router = APIRouter(
    prefix="/user",
    route_class=DishkaRoute,
    tags=["User Limits & History"],
)


@router.get(
    "/limits",
    response_model=UserLimitsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user limits",
    description="Get current user's request limits and usage information."
)
async def get_user_limits(
    service: FromDishka[AIDetectionService],
    current_user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
):
    """
    Get current user's limits and usage.

    Returns information about:
    - Daily request limits
    - Monthly request limits
    - Current usage
    - Remaining quota
    - Premium status
    """
    try:
        logger.info("get_user_limits_request", user_id=current_user.id)

        limits = await service.get_user_limits(current_user.id)

        return UserLimitsResponse(
            daily_limit=limits.daily_limit,
            daily_used=limits.daily_used,
            daily_remaining=limits.daily_remaining,
            daily_reset_at=limits.daily_reset_at,
            monthly_limit=limits.monthly_limit,
            monthly_used=limits.monthly_used,
            monthly_remaining=limits.monthly_remaining,
            monthly_reset_at=limits.monthly_reset_at,
            total_requests=limits.total_requests,
            is_premium=limits.is_premium,
            can_make_request=limits.can_make_request
        )

    except Exception as e:
        logger.error(
            "get_user_limits_failed",
            user_id=current_user.id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user limits"
        )


@router.get(
    "/history",
    response_model=DetectionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get detection history",
    description="Get user's AI detection history with pagination."
)
async def get_detection_history(
    repository: FromDishka[AIDetectionRepository],
    current_user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
    limit: int = Query(50, ge=1, le=100, description="Number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip")
):
    """
    Get detection history for current user.

    **Query Parameters:**
    - `limit`: Maximum number of records (1-100, default: 50)
    - `offset`: Number of records to skip for pagination (default: 0)

    **Returns:**
    List of detection history items with:
    - Detection results
    - Confidence scores
    - Text previews
    - File information (if applicable)
    - Processing times
    """
    try:
        logger.info(
            "get_detection_history_request",
            user_id=current_user.id,
            limit=limit,
            offset=offset
        )

        # Get history records
        history_records = await repository.get_user_history(
            user_id=current_user.id,
            limit=limit,
            offset=offset
        )

        # Get stats for total count
        stats = await repository.get_user_stats(current_user.id)
        total = stats["total_detections"]

        # Convert to response items
        items = [
            DetectionHistoryItem(
                id=record.id,
                source=record.source,
                file_name=record.file_name,
                result=record.result,
                confidence=record.confidence,
                text_preview=record.text_preview[:200],
                created_at=record.created_at,
                processing_time_ms=record.processing_time_ms
            )
            for record in history_records
        ]

        return DetectionHistoryResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset
        )

    except Exception as e:
        logger.error(
            "get_detection_history_failed",
            user_id=current_user.id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch detection history"
        )


@router.get(
    "/stats",
    response_model=UserStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user statistics",
    description="Get aggregated statistics about user's AI detection usage."
)
async def get_user_stats(
    repository: FromDishka[AIDetectionRepository],
    current_user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
):
    """
    Get aggregated statistics for current user.

    **Returns:**
    - Total number of detections
    - Breakdown by result type (AI-generated, human-written, uncertain)
    - Average confidence score
    """
    try:
        logger.info("get_user_stats_request", user_id=current_user.id)

        stats = await repository.get_user_stats(current_user.id)

        return UserStatsResponse(
            total_detections=stats["total_detections"],
            results_breakdown=stats["results_breakdown"],
            average_confidence=stats["average_confidence"]
        )

    except Exception as e:
        logger.error(
            "get_user_stats_failed",
            user_id=current_user.id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user statistics"
        )


@router.delete(
    "/history",
    status_code=status.HTTP_200_OK,
    summary="Delete detection history",
    description="Delete all detection history for current user."
)
async def delete_detection_history(
    repository: FromDishka[AIDetectionRepository],
    current_user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
):
    """
    Delete all detection history for current user.

    **Warning:** This action cannot be undone.

    **Returns:**
    Number of deleted records.
    """
    try:
        logger.info("delete_detection_history_request", user_id=current_user.id)

        deleted_count = await repository.delete_user_history(current_user.id)

        logger.info(
            "delete_detection_history_success",
            user_id=current_user.id,
            deleted_count=deleted_count
        )

        return {
            "message": "Detection history deleted successfully",
            "deleted_count": deleted_count
        }

    except Exception as e:
        logger.error(
            "delete_detection_history_failed",
            user_id=current_user.id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete detection history"
        )