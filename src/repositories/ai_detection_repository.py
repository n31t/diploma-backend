"""
AI Detection repository for database operations.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ai_detection import AIDetectionHistory, UserLimit
from src.core.logging import get_logger

logger = get_logger(__name__)


class AIDetectionRepository:
    """Repository for AI detection related database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ============================================
    # User Limits Management
    # ============================================

    async def get_or_create_user_limit(self, user_id: str) -> UserLimit:
        """
        Get user limit or create default one if doesn't exist.

        Args:
            user_id: User ID

        Returns:
            UserLimit object
        """
        result = await self.session.execute(
            select(UserLimit).where(UserLimit.user_id == user_id)
        )
        user_limit = result.scalar_one_or_none()

        if not user_limit:
            # Create default limit for new user
            now = datetime.now(timezone.utc)
            user_limit = UserLimit(
                user_id=user_id,
                daily_limit=100,
                daily_used=0,
                daily_reset_at=now + timedelta(days=1),
                monthly_limit=1000,
                monthly_used=0,
                monthly_reset_at=now + timedelta(days=30),
                total_requests=0,
                is_premium=False
            )
            self.session.add(user_limit)
            await self.session.flush()
            await self.session.refresh(user_limit)

            logger.info(
                "user_limit_created",
                user_id=user_id,
                daily_limit=user_limit.daily_limit,
                monthly_limit=user_limit.monthly_limit
            )

        return user_limit

    async def check_and_reset_limits(self, user_limit: UserLimit) -> UserLimit:
        """
        Check if limits need to be reset and reset them if necessary.

        Args:
            user_limit: UserLimit object

        Returns:
            Updated UserLimit object
        """
        now = datetime.now(timezone.utc)
        updated = False

        # Reset daily limit if expired
        if now >= user_limit.daily_reset_at:
            user_limit.daily_used = 0
            user_limit.daily_reset_at = now + timedelta(days=1)
            updated = True
            logger.info(
                "daily_limit_reset",
                user_id=user_limit.user_id,
                new_reset_at=user_limit.daily_reset_at
            )

        # Reset monthly limit if expired
        if now >= user_limit.monthly_reset_at:
            user_limit.monthly_used = 0
            user_limit.monthly_reset_at = now + timedelta(days=30)
            updated = True
            logger.info(
                "monthly_limit_reset",
                user_id=user_limit.user_id,
                new_reset_at=user_limit.monthly_reset_at
            )

        if updated:
            await self.session.flush()
            await self.session.refresh(user_limit)

        return user_limit

    async def can_make_request(self, user_id: str) -> tuple[bool, UserLimit]:
        """
        Check if user can make a detection request.

        Args:
            user_id: User ID

        Returns:
            Tuple of (can_make_request: bool, user_limit: UserLimit)
        """
        user_limit = await self.get_or_create_user_limit(user_id)
        user_limit = await self.check_and_reset_limits(user_limit)

        can_request = (
            user_limit.daily_used < user_limit.daily_limit and
            user_limit.monthly_used < user_limit.monthly_limit
        )

        return can_request, user_limit

    async def increment_usage(self, user_id: str) -> UserLimit:
        """
        Increment usage counters for user.

        Args:
            user_id: User ID

        Returns:
            Updated UserLimit object
        """
        user_limit = await self.get_or_create_user_limit(user_id)
        user_limit = await self.check_and_reset_limits(user_limit)

        user_limit.daily_used += 1
        user_limit.monthly_used += 1
        user_limit.total_requests += 1

        await self.session.flush()
        await self.session.refresh(user_limit)

        logger.info(
            "usage_incremented",
            user_id=user_id,
            daily_used=user_limit.daily_used,
            monthly_used=user_limit.monthly_used,
            total_requests=user_limit.total_requests
        )

        return user_limit

    async def update_user_limits(
        self,
        user_id: str,
        daily_limit: Optional[int] = None,
        monthly_limit: Optional[int] = None,
        is_premium: Optional[bool] = None
    ) -> UserLimit:
        """
        Update user limits (for admin operations).

        Args:
            user_id: User ID
            daily_limit: New daily limit (optional)
            monthly_limit: New monthly limit (optional)
            is_premium: Premium status (optional)

        Returns:
            Updated UserLimit object
        """
        user_limit = await self.get_or_create_user_limit(user_id)

        if daily_limit is not None:
            user_limit.daily_limit = daily_limit
        if monthly_limit is not None:
            user_limit.monthly_limit = monthly_limit
        if is_premium is not None:
            user_limit.is_premium = is_premium

        await self.session.flush()
        await self.session.refresh(user_limit)

        logger.info(
            "user_limits_updated",
            user_id=user_id,
            daily_limit=user_limit.daily_limit,
            monthly_limit=user_limit.monthly_limit,
            is_premium=user_limit.is_premium
        )

        return user_limit

    # ============================================
    # Detection History Management
    # ============================================

    async def create_history_record(
        self,
        user_id: str,
        source: str,
        result: str,
        confidence: float,
        text_preview: str,
        text_length: int,
        word_count: int,
        file_name: Optional[str] = None,
        file_size: Optional[int] = None,
        content_type: Optional[str] = None,
        processing_time_ms: Optional[int] = None
    ) -> AIDetectionHistory:
        """
        Create a new detection history record.

        Args:
            user_id: User ID
            source: Detection source ('text' or 'file')
            result: Detection result
            confidence: Confidence score
            text_preview: Text preview (first 500 chars)
            text_length: Total text length
            word_count: Word count
            file_name: File name (optional)
            file_size: File size in bytes (optional)
            content_type: Content type (optional)
            processing_time_ms: Processing time in milliseconds (optional)

        Returns:
            Created AIDetectionHistory object
        """
        history = AIDetectionHistory(
            user_id=user_id,
            source=source,
            result=result,
            confidence=confidence,
            text_preview=text_preview[:500],  # Limit to 500 chars
            text_length=text_length,
            word_count=word_count,
            file_name=file_name,
            file_size=file_size,
            content_type=content_type,
            processing_time_ms=processing_time_ms
        )

        self.session.add(history)
        await self.session.flush()
        await self.session.refresh(history)

        logger.info(
            "detection_history_created",
            user_id=user_id,
            history_id=history.id,
            source=source,
            result=result
        )

        return history

    async def get_user_history(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[AIDetectionHistory]:
        """
        Get user's detection history.

        Args:
            user_id: User ID
            limit: Maximum number of records to return
            offset: Offset for pagination

        Returns:
            List of AIDetectionHistory objects
        """
        result = await self.session.execute(
            select(AIDetectionHistory)
            .where(AIDetectionHistory.user_id == user_id)
            .order_by(AIDetectionHistory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_history_by_id(
        self,
        history_id: str,
        user_id: str
    ) -> Optional[AIDetectionHistory]:
        """
        Get specific history record by ID (with user verification).

        Args:
            history_id: History record ID
            user_id: User ID (for verification)

        Returns:
            AIDetectionHistory object or None
        """
        result = await self.session.execute(
            select(AIDetectionHistory).where(
                and_(
                    AIDetectionHistory.id == history_id,
                    AIDetectionHistory.user_id == user_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_user_stats(self, user_id: str) -> dict:
        """
        Get user statistics.

        Args:
            user_id: User ID

        Returns:
            Dictionary with statistics
        """
        # Total detections
        total_result = await self.session.execute(
            select(func.count(AIDetectionHistory.id))
            .where(AIDetectionHistory.user_id == user_id)
        )
        total = total_result.scalar() or 0

        # Results breakdown
        results_result = await self.session.execute(
            select(
                AIDetectionHistory.result,
                func.count(AIDetectionHistory.id)
            )
            .where(AIDetectionHistory.user_id == user_id)
            .group_by(AIDetectionHistory.result)
        )
        results_breakdown = {row[0]: row[1] for row in results_result.all()}

        # Average confidence
        avg_confidence_result = await self.session.execute(
            select(func.avg(AIDetectionHistory.confidence))
            .where(AIDetectionHistory.user_id == user_id)
        )
        avg_confidence = avg_confidence_result.scalar() or 0.0

        return {
            "total_detections": total,
            "results_breakdown": results_breakdown,
            "average_confidence": round(float(avg_confidence), 3),
        }

    async def delete_user_history(self, user_id: str) -> int:
        """
        Delete all history records for a user.

        Args:
            user_id: User ID

        Returns:
            Number of deleted records
        """
        result = await self.session.execute(
            select(func.count(AIDetectionHistory.id))
            .where(AIDetectionHistory.user_id == user_id)
        )
        count = result.scalar() or 0

        if count > 0:
            await self.session.execute(
                AIDetectionHistory.__table__.delete().where(
                    AIDetectionHistory.user_id == user_id
                )
            )
            await self.session.flush()

            logger.info(
                "user_history_deleted",
                user_id=user_id,
                deleted_count=count
            )

        return count