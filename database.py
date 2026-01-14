"""Database module for managing watchlists."""
import aiosqlite
import logging
from typing import List, Optional, Dict
from datetime import datetime
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


class Database:
    """Handles database operations for watchlists."""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        """Initialize the database.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._initialized = False
    
    async def initialize(self):
        """Initialize the database and create tables if they don't exist."""
        if self._initialized:
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS watched_sets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER,
                    set_code TEXT NOT NULL,
                    last_status TEXT,
                    last_button_detected TEXT,
                    last_checked TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, guild_id, set_code)
                )
            """)
            # Create server_settings table for notification channels
            await db.execute("""
                CREATE TABLE IF NOT EXISTS server_settings (
                    guild_id INTEGER PRIMARY KEY,
                    notification_channel_id INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
            
            # Dynamic migration: Add any missing columns from the expected schema
            # Expected columns and their types (excluding id which is PRIMARY KEY)
            expected_columns = {
                'user_id': 'INTEGER NOT NULL',
                'guild_id': 'INTEGER',
                'set_code': 'TEXT NOT NULL',
                'last_status': 'TEXT',
                'last_button_detected': 'TEXT',
                'last_checked': 'TIMESTAMP',
                'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
            }
            
            # Get current table schema
            cursor = await db.execute("PRAGMA table_info(watched_sets)")
            columns = await cursor.fetchall()
            existing_column_names = {col[1] for col in columns}  # Column name is at index 1
            
            # Add any missing columns
            for column_name, column_type in expected_columns.items():
                if column_name not in existing_column_names:
                    try:
                        await db.execute(f"""
                            ALTER TABLE watched_sets 
                            ADD COLUMN {column_name} {column_type}
                        """)
                        await db.commit()
                        logger.info(f"Added missing column '{column_name}' to existing database")
                    except Exception as e:
                        logger.error(f"Error adding column '{column_name}': {e}")
        
        self._initialized = True
        logger.info(f"Database initialized at {self.db_path}")
    
    async def add_watch(self, user_id: int, set_code: str, guild_id: Optional[int] = None) -> bool:
        """Add a set to a user's watchlist.
        
        Args:
            user_id: Discord user ID
            set_code: LEGO set code
            guild_id: Optional Discord guild/server ID
            
        Returns:
            True if added successfully, False if already exists
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR IGNORE INTO watched_sets (user_id, guild_id, set_code, last_status, last_checked)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, guild_id, set_code, None, None))
                await db.commit()
                
                # Check if row was actually inserted
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM watched_sets
                    WHERE user_id = ? AND guild_id = ? AND set_code = ?
                """, (user_id, guild_id, set_code))
                result = await cursor.fetchone()
                return result[0] > 0
        except Exception as e:
            logger.error(f"Error adding watch: {e}")
            return False
    
    async def remove_watch(self, user_id: int, set_code: str, guild_id: Optional[int] = None) -> bool:
        """Remove a set from a user's watchlist.
        
        Args:
            user_id: Discord user ID
            set_code: LEGO set code
            guild_id: Optional Discord guild/server ID
            
        Returns:
            True if removed successfully, False if not found
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    DELETE FROM watched_sets
                    WHERE user_id = ? AND guild_id = ? AND set_code = ?
                """, (user_id, guild_id, set_code))
                await db.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing watch: {e}")
            return False
    
    async def get_user_watches(self, user_id: int, guild_id: Optional[int] = None) -> List[Dict]:
        """Get all sets a user is watching.
        
        Args:
            user_id: Discord user ID
            guild_id: Optional Discord guild/server ID
            
        Returns:
            List of dictionaries with watch information
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT set_code, last_status, last_checked, created_at
                    FROM watched_sets
                    WHERE user_id = ? AND guild_id = ?
                    ORDER BY created_at DESC
                """, (user_id, guild_id))
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting user watches: {e}")
            return []
    
    async def get_all_watches(self) -> List[Dict]:
        """Get all watched sets across all users.
        
        Returns:
            List of dictionaries with watch information
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT id, user_id, guild_id, set_code, last_status, last_button_detected, last_checked
                    FROM watched_sets
                    ORDER BY last_checked ASC, created_at ASC
                """)
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting all watches: {e}")
            return []
    
    async def update_watch_status(self, watch_id: int, status: str, available: bool, button_detected: Optional[str] = None):
        """Update the last known status of a watched set.
        
        Args:
            watch_id: The watch record ID
            status: The status string (e.g., 'in_stock', 'out_of_stock')
            available: Whether the set is available
            button_detected: The button text that was detected (if any)
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE watched_sets
                    SET last_status = ?, last_button_detected = ?, last_checked = ?
                    WHERE id = ?
                """, (status, button_detected, datetime.now(), watch_id))
                await db.commit()
        except Exception as e:
            logger.error(f"Error updating watch status: {e}")
    
    async def get_watch_by_id(self, watch_id: int) -> Optional[Dict]:
        """Get a watch record by ID.
        
        Args:
            watch_id: The watch record ID
            
        Returns:
            Dictionary with watch information or None if not found
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT id, user_id, guild_id, set_code, last_status, last_button_detected, last_checked
                    FROM watched_sets
                    WHERE id = ?
                """, (watch_id,))
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting watch by ID: {e}")
            return None
    
    async def set_notification_channel(self, guild_id: int, channel_id: int):
        """Set the notification channel for a guild.
        
        Args:
            guild_id: Discord guild/server ID
            channel_id: Discord channel ID for notifications
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO server_settings (guild_id, notification_channel_id, updated_at)
                    VALUES (?, ?, ?)
                """, (guild_id, channel_id, datetime.now()))
                await db.commit()
                logger.info(f"Set notification channel {channel_id} for guild {guild_id}")
        except Exception as e:
            logger.error(f"Error setting notification channel: {e}")
    
    async def get_notification_channel(self, guild_id: int) -> Optional[int]:
        """Get the notification channel ID for a guild.
        
        Args:
            guild_id: Discord guild/server ID
            
        Returns:
            Channel ID if set, None otherwise
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT notification_channel_id FROM server_settings
                    WHERE guild_id = ?
                """, (guild_id,))
                row = await cursor.fetchone()
                return row[0] if row and row[0] else None
        except Exception as e:
            logger.error(f"Error getting notification channel: {e}")
            return None
    
    async def clear_notification_channel(self, guild_id: int):
        """Clear the notification channel for a guild (revert to DMs).
        
        Args:
            guild_id: Discord guild/server ID
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    DELETE FROM server_settings WHERE guild_id = ?
                """, (guild_id,))
                await db.commit()
                logger.info(f"Cleared notification channel for guild {guild_id}")
        except Exception as e:
            logger.error(f"Error clearing notification channel: {e}")

