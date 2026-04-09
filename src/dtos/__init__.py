"""
Data Transfer Objects (DTOs) package.

DTOs are simple dataclasses used to transfer data between layers.
"""

from src.dtos.user_dto import (
    UserRegisterDTO,
    UserLoginDTO,
    UserDTO,
    TokenDTO,
    RefreshTokenDTO,
    AuthenticatedUserDTO,
)
from src.dtos.ai_detection_dto import (
    DetectionSource,
    DetectionResult,
    TextExtractionDTO,
    AIDetectionRequestDTO,
    AIDetectionResultDTO,
)
from src.dtos.normalization_dto import (
    NormalizationMetadata,
    NormalizationResult,
    QualityFlags,
    StructuredBlock,
)

__all__ = [
    "UserRegisterDTO",
    "UserLoginDTO",
    "UserDTO",
    "TokenDTO",
    "RefreshTokenDTO",
    "AuthenticatedUserDTO",
    "DetectionSource",
    "DetectionResult",
    "TextExtractionDTO",
    "AIDetectionRequestDTO",
    "AIDetectionResultDTO",
    "NormalizationMetadata",
    "NormalizationResult",
    "QualityFlags",
    "StructuredBlock",
]
