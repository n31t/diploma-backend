"""
Telegram integration API endpoints.
"""

from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, HTTPException, status, Depends

from src.api.v1.schemas.telegram import TelegramConnectResponse, TelegramStatusResponse
from src.core.logging import get_logger
from src.dtos.user_dto import AuthenticatedUserDTO
from src.services.auth_service import AuthService
from src.services.shared.auth_helpers import get_authenticated_user_dependency

logger = get_logger(__name__)

router = APIRouter(
    prefix="/telegram",
    route_class=DishkaRoute,
    tags=["Telegram"],
)


@router.post(
    "/connect",
    response_model=TelegramConnectResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Telegram connection URL",
    description=(
        "Creates a one-time deep-link that opens the Telegram bot with a "
        "temporary token. The bot will bind the sender's Telegram chat_id to "
        "the current user when /start <token> is received. Token is valid for "
        "TELEGRAM_CONNECT_TOKEN_TTL_MINUTES minutes."
    ),
)
async def generate_telegram_connection_url(
    service: FromDishka[AuthService],
    current_user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
):
    logger.info("generate_telegram_connection_url_request", user_id=current_user.id)
    try:
        dto = await service.generate_telegram_connection_url(user_id=current_user.id)
        return TelegramConnectResponse(bot_url=dto.bot_url)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            "generate_telegram_url_failed",
            user_id=current_user.id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate Telegram connection URL",
        )


@router.get(
    "/status",
    response_model=TelegramStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Telegram connection status",
)
async def get_telegram_status(
    service: FromDishka[AuthService],
    current_user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
):
    logger.info("get_telegram_status_request", user_id=current_user.id)
    try:
        data = await service.get_telegram_status(user_id=current_user.id)
        return TelegramStatusResponse(is_connected=data.is_connected, telegram_chat_id=data.telegram_chat_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "get_telegram_status_failed",
            user_id=current_user.id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get Telegram status",
        )


@router.delete(
    "/disconnect",
    status_code=status.HTTP_200_OK,
    summary="Disconnect Telegram account",
    description="Removes the Telegram chat_id binding from the current user.",
)
async def disconnect_telegram(
    service: FromDishka[AuthService],
    current_user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
):
    logger.info("disconnect_telegram_request", user_id=current_user.id)
    try:
        await service.disconnect_telegram(user_id=current_user.id)
        return {"message": "Telegram account disconnected successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "disconnect_telegram_failed",
            user_id=current_user.id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disconnect Telegram account",
        )