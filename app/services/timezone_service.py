"""
Timezone Service - Centralized timezone conversion and management.

Handles conversion of UTC timestamps to user-specific timezones.
All timestamps are stored in UTC; this service manages display-time conversions.
"""

from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones
from typing import Optional


class TimezoneService:
    """Service for managing user timezone preferences and conversions."""
    
    # Standard IANA timezones grouped by region for UI display
    TIMEZONE_GROUPS = {
        'Asia': [
            'Asia/Kolkata',
            'Asia/Tokyo',
            'Asia/Shanghai',
            'Asia/Hong_Kong',
            'Asia/Bangkok',
            'Asia/Singapore',
            'Asia/Dubai',
            'Asia/Karachi',
            'Asia/Jakarta',
            'Asia/Manila',
            'Asia/Seoul',
            'Asia/Taipei',
        ],
        'Europe': [
            'Europe/London',
            'Europe/Paris',
            'Europe/Berlin',
            'Europe/Madrid',
            'Europe/Amsterdam',
            'Europe/Rome',
            'Europe/Athens',
            'Europe/Moscow',
            'Europe/Istanbul',
            'Europe/Lisbon',
        ],
        'Americas': [
            'America/New_York',
            'America/Chicago',
            'America/Denver',
            'America/Los_Angeles',
            'America/Toronto',
            'America/Vancouver',
            'America/Mexico_City',
            'America/Sao_Paulo',
            'America/Buenos_Aires',
            'America/Caracas',
        ],
        'Pacific': [
            'Pacific/Auckland',
            'Pacific/Sydney',
            'Pacific/Fiji',
            'Pacific/Honolulu',
        ],
        'Africa': [
            'Africa/Cairo',
            'Africa/Johannesburg',
            'Africa/Lagos',
            'Africa/Nairobi',
            'Africa/Casablanca',
        ],
        'UTC': [
            'UTC',
            'Etc/UTC',
        ]
    }

    @staticmethod
    def get_all_timezones() -> dict:
        """
        Get all available timezones grouped by region.
        
        Returns:
            dict: Grouped timezone dictionaries with region as key and list of timezones as value.
        """
        return TimezoneService.TIMEZONE_GROUPS

    @staticmethod
    def get_timezone_list() -> list:
        """
        Get a flat list of all available timezones.
        
        Returns:
            list: All IANA timezone identifiers.
        """
        all_timezones = []
        for group in TimezoneService.TIMEZONE_GROUPS.values():
            all_timezones.extend(group)
        return sorted(set(all_timezones))

    @staticmethod
    def is_valid_timezone(timezone_str: str) -> bool:
        """
        Validate if a timezone string is valid.
        
        Args:
            timezone_str: IANA timezone identifier (e.g., 'Asia/Kolkata').
            
        Returns:
            bool: True if timezone is valid, False otherwise.
        """
        try:
            ZoneInfo(timezone_str)
            return True
        except (KeyError, ValueError):
            return False

    @staticmethod
    def convert_to_user_timezone(
        dt_utc: datetime,
        user_timezone: str = 'UTC'
    ) -> datetime:
        """
        Convert a UTC datetime to a user's timezone.
        
        Args:
            dt_utc: Datetime object in UTC. Can be naive (assumed UTC) or aware.
            user_timezone: IANA timezone string (e.g., 'Asia/Kolkata'). Defaults to UTC.
            
        Returns:
            datetime: Timezone-aware datetime in the user's timezone.
            
        Raises:
            ValueError: If timezone is invalid.
        """
        # Ensure input datetime is aware and in UTC
        if dt_utc is None:
            return None
            
        if dt_utc.tzinfo is None:
            # Assume naive datetime is UTC
            dt_utc = dt_utc.replace(tzinfo=ZoneInfo('UTC'))
        
        # Validate user timezone
        if not TimezoneService.is_valid_timezone(user_timezone):
            user_timezone = 'UTC'
        
        # Convert to user timezone
        user_tz = ZoneInfo(user_timezone)
        return dt_utc.astimezone(user_tz)

    @staticmethod
    def convert_to_utc(
        dt_local: datetime,
        user_timezone: str = 'UTC'
    ) -> datetime:
        """
        Convert a local datetime to UTC.
        
        Args:
            dt_local: Datetime object in user's local timezone. Can be naive or aware.
            user_timezone: IANA timezone string of the local datetime.
            
        Returns:
            datetime: Timezone-aware datetime in UTC.
            
        Raises:
            ValueError: If timezone is invalid.
        """
        if dt_local is None:
            return None
            
        # Validate user timezone
        if not TimezoneService.is_valid_timezone(user_timezone):
            user_timezone = 'UTC'
        
        if dt_local.tzinfo is None:
            # Assume naive datetime is in user's timezone
            user_tz = ZoneInfo(user_timezone)
            dt_local = dt_local.replace(tzinfo=user_tz)
        
        # Convert to UTC
        utc_tz = ZoneInfo('UTC')
        return dt_local.astimezone(utc_tz)

    @staticmethod
    def format_datetime_for_user(
        dt_utc: datetime,
        user_timezone: str = 'UTC',
        format_string: str = '%b %d, %Y at %I:%M %p'
    ) -> str:
        """
        Format a UTC datetime for display to a user in their timezone.
        
        Args:
            dt_utc: UTC datetime to format.
            user_timezone: User's IANA timezone.
            format_string: Python strftime format string.
            
        Returns:
            str: Formatted datetime string in user's timezone.
        """
        if dt_utc is None:
            return 'N/A'
            
        user_dt = TimezoneService.convert_to_user_timezone(dt_utc, user_timezone)
        return user_dt.strftime(format_string)

    @staticmethod
    def format_date_for_user(
        dt_utc: datetime,
        user_timezone: str = 'UTC',
        format_string: str = '%b %d, %Y'
    ) -> str:
        """
        Format a UTC datetime as a date (without time) for display to a user.
        
        Args:
            dt_utc: UTC datetime to format.
            user_timezone: User's IANA timezone.
            format_string: Python strftime format string.
            
        Returns:
            str: Formatted date string in user's timezone.
        """
        if dt_utc is None:
            return 'N/A'
            
        user_dt = TimezoneService.convert_to_user_timezone(dt_utc, user_timezone)
        return user_dt.strftime(format_string)

    @staticmethod
    def get_timezone_offset_str(user_timezone: str = 'UTC') -> str:
        """
        Get the current UTC offset string for a timezone.
        
        Args:
            user_timezone: IANA timezone identifier.
            
        Returns:
            str: UTC offset string (e.g., 'UTC+5:30', 'UTC-8:00').
        """
        if not TimezoneService.is_valid_timezone(user_timezone):
            user_timezone = 'UTC'
            
        tz = ZoneInfo(user_timezone)
        now = datetime.now(tz)
        offset = now.strftime('%z')
        
        # Format offset as UTC±HH:MM
        if offset == '+0000' or offset == '-0000':
            return 'UTC'
        
        sign = offset[0]
        hours = offset[1:3]
        minutes = offset[3:5]
        
        # Remove leading zero from hours if present
        hours = str(int(hours))
        
        if minutes == '00':
            return f'UTC{sign}{hours}'
        else:
            return f'UTC{sign}{hours}:{minutes}'
