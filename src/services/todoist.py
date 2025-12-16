"""Todoist API service implementation"""

import os
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from zoneinfo import ZoneInfo
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task, Project, Section, Label, Comment
from typing import TYPE_CHECKING

from .cache import RedisCache, cache_aside, CacheConfig, CacheTTL

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)


class TodoistService:
    """Complete Todoist API service implementation"""

    def __init__(
        self,
        api_token: Optional[str] = None,
        mcp: Optional["FastMCP"] = None,
        cache: Optional[RedisCache] = None,
    ):
        """
        Initialize Todoist service

        Args:
            api_token: Todoist API token (or from TODOIST_API_TOKEN env var)
            mcp: FastMCP server instance
            cache: Redis cache instance (optional)
        """
        self.api_token = api_token or os.getenv("TODOIST_API_TOKEN")
        if not self.api_token:
            raise ValueError("Todoist API token is required")

        self.api = TodoistAPI(self.api_token)
        self.mcp = mcp

        # Initialize cache if not provided
        self.cache = cache
        if self.cache is None:
            self.cache = RedisCache.from_env()

        # Get timezone from environment, default to US/Eastern
        self.timezone_str = os.getenv("TIMEZONE", "US/Eastern")
        try:
            self.timezone = ZoneInfo(self.timezone_str)
        except Exception as exc:
            logger.warning(
                "Invalid timezone '%s', using US/Eastern: %s",
                self.timezone_str,
                exc,
            )
            self.timezone = ZoneInfo("US/Eastern")

        logger.info(
            f"Todoist service initialized (cache: {'enabled' if self.cache else 'disabled'}, timezone: {self.timezone_str})"
        )

        # Register MCP tools if MCP server is provided
        if self.mcp:
            self._register_mcp_tools()

    # ========== VALIDATION HELPERS ==========

    def _validate_priority(self, priority: Optional[int]) -> Optional[int]:
        """Validate priority value and return as integer"""
        if priority is not None:
            # Convert to int if string
            try:
                priority_int = int(priority)
            except (ValueError, TypeError):
                raise ValueError(
                    f"Invalid priority value: {priority}. Priority must be an integer between 1-4.\n"
                    "Use `get_todoist_priorities` tool to see all available priority levels."
                )

            if priority_int not in [1, 2, 3, 4]:
                raise ValueError(
                    f"Invalid priority value: {priority_int}. Priority must be between 1-4, where:\n"
                    "  • 4 = Urgent/P1 (red) - Highest priority\n"
                    "  • 3 = High/P2 (orange)\n"
                    "  • 2 = Medium/P3 (blue)\n"
                    "  • 1 = Normal/P4 (gray) - Default priority\n"
                    "Note: In Todoist, higher numbers mean higher priority.\n"
                    "Use `get_todoist_priorities` tool to see all available priority levels."
                )
            return priority_int
        return None

    def _validate_duration_unit(self, duration_unit: Optional[str]) -> None:
        """Validate duration unit"""
        if duration_unit is not None and duration_unit not in ["minute", "day"]:
            raise ValueError(
                f"Invalid duration_unit: '{duration_unit}'. Duration unit must be either 'minute' or 'day'.\n"
                "Examples:\n"
                "  • duration=30, duration_unit='minute' for a 30-minute task\n"
                "  • duration=2, duration_unit='day' for a 2-day task"
            )

    def _validate_project_id(self, project_id: Optional[str]) -> None:
        """Validate project ID exists"""
        if project_id is not None:
            try:
                # Try to get the project to verify it exists
                self.api.get_project(project_id)
            except Exception as e:
                raise ValueError(
                    f"Invalid project_id: '{project_id}'. This project does not exist or is not accessible.\n"
                    "To find valid project IDs:\n"
                    "  • Use `get_todoist_projects` tool to list all available projects\n"
                    "  • Check if the project might be archived\n"
                    f"Original error: {str(e)}"
                )

    def _validate_section_id(self, section_id: Optional[str]) -> None:
        """Validate section ID exists"""
        if section_id is not None:
            try:
                # Try to get the section to verify it exists
                self.api.get_section(section_id)
            except Exception as e:
                raise ValueError(
                    f"Invalid section_id: '{section_id}'. This section does not exist or is not accessible.\n"
                    "To find valid section IDs:\n"
                    "  • Use `get_sections` with the project_id parameter to list sections in a project\n"
                    "  • Ensure the section belongs to the correct project\n"
                    f"Original error: {str(e)}"
                )

    def _validate_label_names(self, labels: Optional[List[str]]) -> None:
        """Validate label names exist"""
        if labels is not None:
            try:
                existing_labels = self.get_labels()
                existing_names = [label["name"] for label in existing_labels]
                invalid_labels = [
                    label_name
                    for label_name in labels
                    if label_name not in existing_names
                ]
                if invalid_labels:
                    raise ValueError(
                        f"Invalid label(s): {', '.join(invalid_labels)}. These labels do not exist.\n"
                        f"Available labels: {', '.join(existing_names)}\n"
                        "To create new labels:\n"
                        "  • Use `create_todoist_label` tool to create missing labels first\n"
                        "  • Or use `get_todoist_labels` tool to see all available labels"
                    )
            except ValueError:
                raise
            except Exception as e:
                logger.warning(f"Could not validate labels: {e}")

    def _validate_due_date_format(self, due_date: Optional[str]) -> None:
        """Validate due date format"""
        if due_date is not None:
            try:
                datetime.strptime(due_date, "%Y-%m-%d")
            except ValueError:
                raise ValueError(
                    f"Invalid due_date format: '{due_date}'. Date must be in YYYY-MM-DD format.\n"
                    "Examples:\n"
                    "  • '2024-12-31' for December 31, 2024\n"
                    "  • '2024-01-15' for January 15, 2024\n"
                    "Alternatively:\n"
                    "  • Use due_string with natural language like 'tomorrow', 'next Friday', 'in 2 weeks'"
                )

    def _validate_color(self, color: Optional[str]) -> None:
        """Validate color value"""
        valid_colors = [
            "berry_red",
            "red",
            "orange",
            "yellow",
            "olive_green",
            "lime_green",
            "green",
            "mint_green",
            "teal",
            "sky_blue",
            "light_blue",
            "blue",
            "grape",
            "violet",
            "lavender",
            "magenta",
            "salmon",
            "charcoal",
            "grey",
            "taupe",
        ]
        if color is not None and color not in valid_colors:
            raise ValueError(
                f"Invalid color: '{color}'.\n"
                f"Available colors: {', '.join(valid_colors)}\n"
                "Use `get_todoist_colors` tool to see all available colors with their descriptions."
            )

    def _validate_view_style(self, view_style: Optional[str]) -> None:
        """Validate view style"""
        if view_style is not None and view_style not in ["list", "board"]:
            raise ValueError(
                f"Invalid view_style: '{view_style}'. View style must be either 'list' or 'board'.\n"
                "  • 'list' - Traditional list view\n"
                "  • 'board' - Kanban board view"
            )

    # ========== TASK OPERATIONS ==========

    def get_tasks_with_filter(
        self, filter_query: str, lang: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get tasks using Todoist's native filter API which properly handles timezone-aware queries

        Args:
            filter_query: Todoist filter query (e.g., "today", "tomorrow", "next 7 days")
            lang: Language for filter parsing (optional)
            limit: Maximum number of results (optional, max 200)

        Returns:
            List of task dictionaries matching the filter
        """
        try:
            # Use the native filter_tasks API which handles timezone conversions properly
            task_iterator = self.api.filter_tasks(
                query=filter_query, lang=lang, limit=limit
            )

            # Flatten the iterator results
            all_tasks = []
            for task_batch in task_iterator:
                if isinstance(task_batch, list):
                    for task in task_batch:
                        all_tasks.append(self._task_to_dict(task))
                else:
                    all_tasks.append(self._task_to_dict(task_batch))

            return all_tasks
        except Exception as e:
            logger.error(f"Failed to get tasks with filter '{filter_query}': {e}")
            # Fall back to manual filtering if filter API fails
            logger.warning(
                f"Falling back to manual filtering for query: {filter_query}"
            )
            return self._manual_filter_tasks(filter_query)

    def _manual_filter_tasks(self, filter_query: str) -> List[Dict[str, Any]]:
        """
        Manual fallback for filtering tasks when filter API is not available
        """
        tasks = self.get_tasks()
        today = datetime.now(self.timezone).date()

        # Simple filter implementations
        if filter_query == "today":
            return [t for t in tasks if self._is_due_on_date(t, today)]
        elif filter_query == "tomorrow":
            tomorrow = today + timedelta(days=1)
            return [t for t in tasks if self._is_due_on_date(t, tomorrow)]
        elif filter_query == "overdue":
            return [t for t in tasks if self._is_overdue(t, today)]
        elif filter_query == "next 7 days" or filter_query == "7 days":
            week_end = today + timedelta(days=6)
            return [t for t in tasks if self._is_due_between(t, today, week_end)]
        elif filter_query == "no date":
            return [t for t in tasks if not t.get("due")]
        else:
            logger.warning(
                f"Unsupported manual filter: {filter_query}, returning all tasks"
            )
            return tasks

    def _is_due_on_date(self, task: Dict[str, Any], target_date: date) -> bool:
        """Check if task is due on specific date"""
        if not task.get("due"):
            return False
        task_date = self._extract_task_date(task)
        return task_date == target_date if task_date else False

    def _is_overdue(self, task: Dict[str, Any], today: date) -> bool:
        """Check if task is overdue"""
        if not task.get("due"):
            return False
        task_date = self._extract_task_date(task)
        return task_date < today if task_date else False

    def _is_due_between(
        self, task: Dict[str, Any], start_date: date, end_date: date
    ) -> bool:
        """Check if task is due between two dates"""
        if not task.get("due"):
            return False
        task_date = self._extract_task_date(task)
        return start_date <= task_date <= end_date if task_date else False

    def _extract_task_date(self, task: Dict[str, Any]) -> Optional[date]:
        """Extract date from task's due field, handling timezone conversion"""
        due_info = task.get("due")
        if not due_info:
            return None

        # Try datetime field first (more precise)
        if due_info.get("datetime"):
            datetime_val = due_info["datetime"]
            try:
                if isinstance(datetime_val, str):
                    task_dt = datetime.fromisoformat(
                        datetime_val.replace("Z", "+00:00")
                    )
                    task_dt = task_dt.astimezone(self.timezone)
                    return task_dt.date()
                elif isinstance(datetime_val, datetime):
                    return datetime_val.astimezone(self.timezone).date()
                elif isinstance(datetime_val, date):
                    return datetime_val
            except Exception as e:
                logger.debug(f"Failed to parse datetime '{datetime_val}': {e}")

        # Fall back to date field
        if due_info.get("date"):
            date_val = due_info["date"]
            try:
                if isinstance(date_val, date):
                    return date_val
                elif isinstance(date_val, datetime):
                    return date_val.date()
                elif isinstance(date_val, str):
                    if "T" in date_val:
                        task_dt = datetime.fromisoformat(
                            date_val.replace("Z", "+00:00")
                        )
                        task_dt = task_dt.astimezone(self.timezone)
                        return task_dt.date()
                    else:
                        return datetime.strptime(date_val, "%Y-%m-%d").date()
            except Exception as e:
                logger.debug(f"Failed to parse date '{date_val}': {e}")

        return None

    @cache_aside(CacheConfig(ttl=CacheTTL.TODOIST_TASKS, key_prefix="todoist:tasks"))
    def get_tasks(
        self,
        project_id: Optional[str] = None,
        section_id: Optional[str] = None,
        label: Optional[str] = None,
        filter_str: Optional[str] = None,
        lang: Optional[str] = None,
        ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get all active tasks with optional filters

        Args:
            project_id: Filter by project
            section_id: Filter by section
            label: Filter by label name
            filter_str: Todoist filter query (e.g., "today", "p1", "overdue")
            lang: Language for filter parsing
            ids: List of specific task IDs to fetch
            limit: Maximum number of results to return (for pagination)
            offset: Number of results to skip (for pagination)

        Returns:
            List of task dictionaries
        """
        try:
            # Note: The Todoist API doesn't support filter parameter directly
            # Filters like "today", "overdue" need to be handled differently
            # For now, we'll ignore the filter parameter and get all tasks
            if filter_str:
                logger.warning(
                    f"Filter '{filter_str}' not directly supported by API, returning all tasks"
                )

            task_iterator = self.api.get_tasks(
                project_id=project_id, section_id=section_id, label=label, ids=ids
            )
            # The API returns an iterator of lists, we need to flatten it
            all_tasks = []
            for task_batch in task_iterator:
                for task in task_batch:
                    all_tasks.append(self._task_to_dict(task))

            # Apply pagination
            if limit is not None:
                end_index = offset + limit
                all_tasks = all_tasks[offset:end_index]
            elif offset > 0:
                all_tasks = all_tasks[offset:]

            return all_tasks
        except Exception as e:
            logger.error(f"Failed to get tasks: {e}")
            raise

    def get_task(self, task_id: str) -> Dict[str, Any]:
        """Get a specific task by ID"""
        try:
            task = self.api.get_task(task_id)
            return self._task_to_dict(task)
        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {e}")
            raise

    def create_task(
        self,
        content: str,
        description: Optional[str] = None,
        project_id: Optional[str] = None,
        section_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        order: Optional[int] = None,
        labels: Optional[List[str]] = None,
        priority: Optional[int] = None,
        due_string: Optional[str] = None,
        due_date: Optional[str] = None,
        due_datetime: Optional[str] = None,
        due_lang: Optional[str] = None,
        deadline_date: Optional[str] = None,  # NATIVE DEADLINE FIELD
        deadline_lang: Optional[str] = None,
        assignee_id: Optional[str] = None,
        duration: Optional[int] = None,
        duration_unit: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new task

        Args:
            content: Task content/title
            description: Task description
            project_id: Project to add task to
            section_id: Section within project
            parent_id: Parent task ID for subtasks
            order: Position in list
            labels: List of label names
            priority: Priority (1-4, where 4 is urgent)
            due_string: Natural language due date
            due_date: Specific due date (YYYY-MM-DD)
            due_datetime: Specific due datetime (RFC3339)
            due_lang: Language for due_string parsing
            assignee_id: User ID to assign to
            duration: Estimated duration
            duration_unit: Duration unit (minute or day)

        Returns:
            Created task dictionary
        """
        # Validate parameters and convert types
        priority = self._validate_priority(priority)  # Returns integer or None
        self._validate_duration_unit(duration_unit)
        self._validate_project_id(project_id)
        self._validate_section_id(section_id)
        self._validate_label_names(labels)
        self._validate_due_date_format(due_date)
        self._validate_due_date_format(deadline_date)  # Validate deadline format too

        # Convert date strings to date objects for API
        from datetime import datetime

        if due_date is not None:
            due_date_obj = datetime.strptime(due_date, "%Y-%m-%d").date()
        else:
            due_date_obj = None

        if deadline_date is not None:
            deadline_date_obj = datetime.strptime(deadline_date, "%Y-%m-%d").date()
        else:
            deadline_date_obj = None

        try:
            task = self.api.add_task(
                content=content,
                description=description,
                project_id=project_id,
                section_id=section_id,
                parent_id=parent_id,
                order=order,
                labels=labels,
                priority=priority,
                due_string=due_string,
                due_date=due_date_obj,  # Pass date object
                due_datetime=due_datetime,
                due_lang=due_lang,
                deadline_date=deadline_date_obj,  # Pass date object
                deadline_lang=deadline_lang,
                assignee_id=assignee_id,
                duration=duration,
                duration_unit=duration_unit,
            )

            # Invalidate cache for tasks after creation
            if self.cache:
                self.cache.delete_pattern("todoist:tasks:*")

            return self._task_to_dict(task)
        except ValueError:
            # Re-raise validation errors with their helpful messages
            raise
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            # Provide helpful error message based on common issues
            if "404" in str(e) or "not found" in str(e).lower():
                raise ValueError(
                    f"Failed to create task: Resource not found.\n"
                    "Possible issues:\n"
                    "  • Project ID might be invalid - use `get_todoist_projects` to verify\n"
                    "  • Section ID might be invalid - use `get_sections` to verify\n"
                    "  • Parent task ID might be invalid\n"
                    f"Original error: {str(e)}"
                )
            elif "401" in str(e) or "unauthorized" in str(e).lower():
                raise ValueError(
                    "Authentication failed. Please check your Todoist API token.\n"
                    "To fix:\n"
                    "  • Verify TODOIST_API_TOKEN environment variable is set correctly\n"
                    "  • Generate a new token at todoist.com/prefs/integrations\n"
                    f"Original error: {str(e)}"
                )
            else:
                raise ValueError(
                    f"Failed to create task: {str(e)}\n"
                    "For help with common issues:\n"
                    "  • Use `get_todoist_projects` to find valid project IDs\n"
                    "  • Use `get_todoist_labels` to see available labels\n"
                    "  • Use `get_todoist_priorities` for priority information"
                )

    def update_task(
        self,
        task_id: str,
        content: Optional[str] = None,
        description: Optional[str] = None,
        labels: Optional[List[str]] = None,
        priority: Optional[int] = None,
        due_string: Optional[str] = None,
        due_date: Optional[str] = None,
        due_datetime: Optional[str] = None,
        due_lang: Optional[str] = None,
        deadline_date: Optional[str] = None,  # NATIVE DEADLINE FIELD
        deadline_lang: Optional[str] = None,
        assignee_id: Optional[str] = None,
        duration: Optional[int] = None,
        duration_unit: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing task

        Args:
            task_id: ID of task to update
            Other args same as create_task

        Returns:
            Updated task dictionary
        """
        # Validate parameters and convert types
        priority = self._validate_priority(priority)  # Returns integer or None
        self._validate_duration_unit(duration_unit)
        self._validate_label_names(labels)
        self._validate_due_date_format(due_date)
        self._validate_due_date_format(deadline_date)  # Validate deadline format too

        # Convert date strings to date objects for API
        from datetime import datetime

        if due_date is not None:
            due_date_obj = datetime.strptime(due_date, "%Y-%m-%d").date()
        else:
            due_date_obj = None

        if deadline_date is not None:
            deadline_date_obj = datetime.strptime(deadline_date, "%Y-%m-%d").date()
        else:
            deadline_date_obj = None

        try:
            task = self.api.update_task(
                task_id=task_id,
                content=content,
                description=description,
                labels=labels,
                priority=priority,
                due_string=due_string,
                due_date=due_date_obj,  # Pass date object
                due_datetime=due_datetime,
                due_lang=due_lang,
                deadline_date=deadline_date_obj,  # Pass date object
                deadline_lang=deadline_lang,
                assignee_id=assignee_id,
                duration=duration,
                duration_unit=duration_unit,
            )
            return self._task_to_dict(task)
        except ValueError:
            # Re-raise validation errors with their helpful messages
            raise
        except Exception as e:
            logger.error(f"Failed to update task {task_id}: {e}")
            if "404" in str(e) or "not found" in str(e).lower():
                raise ValueError(
                    f"Failed to update task: Task with ID '{task_id}' not found.\n"
                    "To fix:\n"
                    "  • Use `get_todoist_tasks` to find the correct task ID\n"
                    "  • Verify the task hasn't been deleted\n"
                    f"Original error: {str(e)}"
                )
            else:
                raise ValueError(
                    f"Failed to update task: {str(e)}\n"
                    "For help:\n"
                    "  • Use `get_todoist_tasks` to verify the task exists\n"
                    "  • Check parameter formats match the requirements"
                )

    def close_task(self, task_id: str) -> bool:
        """Mark a task as completed"""
        try:
            # The Todoist API uses 'complete_task()'
            return self.api.complete_task(task_id=task_id)
        except Exception as e:
            logger.error(f"Failed to close task {task_id}: {e}")
            raise

    def reopen_task(self, task_id: str) -> bool:
        """Reopen a completed task"""
        try:
            # The Todoist API uses 'uncomplete_task()'
            return self.api.uncomplete_task(task_id=task_id)
        except Exception as e:
            logger.error(f"Failed to reopen task {task_id}: {e}")
            raise

    def delete_task(self, task_id: str) -> bool:
        """Delete a task permanently"""
        try:
            return self.api.delete_task(task_id)
        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {e}")
            raise

    def move_task(
        self,
        task_id: str,
        project_id: Optional[str] = None,
        section_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Move a task to a different project, section, or parent task.

        Args:
            task_id: ID of task to move
            project_id: Target project ID (moves to project root)
            section_id: Target section ID (moves to section within its project)
            parent_id: Target parent task ID (makes this a subtask)

        Note: Only one of project_id, section_id, or parent_id should be set.
              To move from a section to project root, use project_id.

        Returns:
            Updated task dictionary
        """
        # Validate that exactly one target is specified
        targets = [project_id, section_id, parent_id]
        specified = [t for t in targets if t is not None]
        if len(specified) != 1:
            raise ValueError(
                "Exactly one of project_id, section_id, or parent_id must be specified.\n"
                "Examples:\n"
                "  • Move to project: project_id='123'\n"
                "  • Move to section: section_id='456'\n"
                "  • Make subtask: parent_id='789'"
            )

        # Validate the target exists
        if project_id:
            self._validate_project_id(project_id)
        if section_id:
            self._validate_section_id(section_id)

        try:
            # Use SDK's native move_task method
            task = self.api.move_task(
                task_id=task_id,
                project_id=project_id,
                section_id=section_id,
                parent_id=parent_id,
            )

            # Invalidate task cache after move
            if self.cache:
                self.cache.delete_pattern("todoist:tasks:*")

            return self._task_to_dict(task)

        except Exception as e:
            logger.error(f"Failed to move task {task_id}: {e}")
            if "404" in str(e) or "not found" in str(e).lower():
                raise ValueError(
                    f"Failed to move task: Task or target not found.\n"
                    "To fix:\n"
                    "  • Use `get_todoist_tasks` to verify the task exists\n"
                    "  • Use `get_todoist_projects` to verify project ID\n"
                    f"Original error: {str(e)}"
                )
            raise

    def quick_add_task(self, text: str) -> Dict[str, Any]:
        """
        Create a task using Todoist's Quick Add syntax.

        Supports natural language like:
        - "Buy milk tomorrow p1 #Shopping @errands"
        - "Meeting with John every Monday at 10am"
        - "Submit report by Friday #Work"

        Args:
            text: Quick add text with natural language date, project, labels, priority

        Returns:
            Created task dictionary
        """
        try:
            task = self.api.add_task_quick(text=text)

            # Invalidate task cache after creation
            if self.cache:
                self.cache.delete_pattern("todoist:tasks:*")

            return self._task_to_dict(task)
        except Exception as e:
            logger.error(f"Failed to quick add task: {e}")
            raise

    def get_completed_tasks(
        self,
        project_id: Optional[str] = None,
        section_id: Optional[str] = None,
        item_id: Optional[str] = None,
        last_seen_id: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get completed tasks by completion date.

        Args:
            project_id: Filter by project
            section_id: Filter by section
            item_id: Filter by specific task
            last_seen_id: For pagination
            limit: Max results (default 50)
            cursor: Pagination cursor

        Returns:
            Dict with completed tasks and pagination info
        """
        try:
            result = self.api.get_completed_tasks_by_completion_date(
                project_id=project_id,
                section_id=section_id,
                item_id=item_id,
                last_seen_id=last_seen_id,
                limit=limit,
                cursor=cursor,
            )
            return {
                "items": [self._task_to_dict(t) for t in result.items],
                "cursor": getattr(result, "cursor", None),
                "has_more": getattr(result, "has_more", False),
            }
        except Exception as e:
            logger.error(f"Failed to get completed tasks: {e}")
            raise

    def get_completed_tasks_by_due_date(
        self,
        due_date: str,
        project_id: Optional[str] = None,
        timezone: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Get completed tasks that were due on a specific date.

        Args:
            due_date: Due date in YYYY-MM-DD format
            project_id: Filter by project
            timezone: Timezone for date interpretation
            cursor: Pagination cursor
            limit: Max results (default 50)

        Returns:
            Dict with completed tasks and pagination info
        """
        self._validate_due_date_format(due_date)

        try:
            result = self.api.get_completed_tasks_by_due_date(
                due_date=due_date,
                project_id=project_id,
                timezone=timezone or self.timezone_str,
                cursor=cursor,
                limit=limit,
            )
            return {
                "items": [self._task_to_dict(t) for t in result.items],
                "cursor": getattr(result, "cursor", None),
                "has_more": getattr(result, "has_more", False),
            }
        except Exception as e:
            logger.error(f"Failed to get completed tasks by due date: {e}")
            raise

    # ========== PROJECT OPERATIONS ==========

    @cache_aside(
        CacheConfig(ttl=CacheTTL.TODOIST_PROJECTS, key_prefix="todoist:projects")
    )
    def get_projects(self) -> List[Dict[str, Any]]:
        """Get all projects"""
        try:
            projects_paginator = self.api.get_projects()
            # The paginator returns lists of projects, we need to flatten it
            all_projects = []
            for project_batch in projects_paginator:
                if isinstance(project_batch, list):
                    all_projects.extend(project_batch)
                else:
                    all_projects.append(project_batch)
            return [self._project_to_dict(p) for p in all_projects]
        except Exception as e:
            logger.error(f"Failed to get projects: {e}")
            raise

    def get_project(self, project_id: str) -> Dict[str, Any]:
        """Get a specific project"""
        try:
            project = self.api.get_project(project_id)
            return self._project_to_dict(project)
        except Exception as e:
            logger.error(f"Failed to get project {project_id}: {e}")
            raise

    def create_project(
        self,
        name: str,
        parent_id: Optional[str] = None,
        color: Optional[str] = None,
        is_favorite: bool = False,
        view_style: str = "list",
    ) -> Dict[str, Any]:
        """
        Create a new project

        Args:
            name: Project name
            parent_id: Parent project ID for subprojects
            color: Color name or hex code
            is_favorite: Mark as favorite
            view_style: "list" or "board"

        Returns:
            Created project dictionary
        """
        # Validate parameters
        self._validate_color(color)
        self._validate_view_style(view_style)
        self._validate_project_id(parent_id)  # Validate parent exists if provided

        try:
            project = self.api.add_project(
                name=name,
                parent_id=parent_id,
                color=color,
                is_favorite=is_favorite,
                view_style=view_style,
            )
            return self._project_to_dict(project)
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            raise

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        color: Optional[str] = None,
        is_favorite: Optional[bool] = None,
        view_style: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing project"""
        # Validate parameters
        self._validate_color(color)
        self._validate_view_style(view_style)

        try:
            project = self.api.update_project(
                project_id=project_id,
                name=name,
                color=color,
                is_favorite=is_favorite,
                view_style=view_style,
            )

            # Invalidate cache for projects after update
            if self.cache:
                self.cache.delete_pattern("todoist:projects:*")

            return self._project_to_dict(project)
        except Exception as e:
            logger.error(f"Failed to update project {project_id}: {e}")
            raise

    def delete_project(self, project_id: str) -> bool:
        """Delete a project"""
        try:
            result = self.api.delete_project(project_id)

            # Invalidate caches after deletion
            if self.cache:
                self.cache.delete_pattern("todoist:projects:*")
                self.cache.delete_pattern("todoist:tasks:*")
                self.cache.delete_pattern("todoist:sections:*")

            return result
        except Exception as e:
            logger.error(f"Failed to delete project {project_id}: {e}")
            raise

    def archive_project(self, project_id: str) -> bool:
        """Archive a project"""
        try:
            result = self.api.archive_project(project_id)

            # Invalidate project cache after archiving
            if self.cache:
                self.cache.delete_pattern("todoist:projects:*")

            return result
        except Exception as e:
            logger.error(f"Failed to archive project {project_id}: {e}")
            raise

    def unarchive_project(self, project_id: str) -> bool:
        """Unarchive a project"""
        try:
            result = self.api.unarchive_project(project_id)

            # Invalidate project cache after unarchiving
            if self.cache:
                self.cache.delete_pattern("todoist:projects:*")

            return result
        except Exception as e:
            logger.error(f"Failed to unarchive project {project_id}: {e}")
            raise

    def get_collaborators(self, project_id: str) -> List[Dict[str, Any]]:
        """Get collaborators for a shared project"""
        try:
            collaborators = self.api.get_collaborators(project_id=project_id)
            return [
                {
                    "id": c.id,
                    "name": c.name,
                    "email": c.email,
                }
                for c in collaborators
            ]
        except Exception as e:
            logger.error(f"Failed to get collaborators for project {project_id}: {e}")
            raise

    # ========== SECTION OPERATIONS ==========

    @cache_aside(
        CacheConfig(ttl=CacheTTL.TODOIST_SECTIONS, key_prefix="todoist:sections")
    )
    def get_sections(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get sections, optionally filtered by project"""
        try:
            sections_paginator = self.api.get_sections(project_id=project_id)
            # The paginator returns lists of sections, we need to flatten it
            all_sections = []
            for section_batch in sections_paginator:
                if isinstance(section_batch, list):
                    all_sections.extend(section_batch)
                else:
                    all_sections.append(section_batch)
            return [self._section_to_dict(s) for s in all_sections]
        except Exception as e:
            logger.error(f"Failed to get sections: {e}")
            raise

    def get_section(self, section_id: str) -> Dict[str, Any]:
        """Get a specific section"""
        try:
            section = self.api.get_section(section_id)
            return self._section_to_dict(section)
        except Exception as e:
            logger.error(f"Failed to get section {section_id}: {e}")
            raise

    def create_section(
        self, name: str, project_id: str, order: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a new section in a project"""
        try:
            section = self.api.add_section(
                name=name, project_id=project_id, order=order
            )

            # Invalidate section cache after creation
            if self.cache:
                self.cache.delete_pattern("todoist:sections:*")

            return self._section_to_dict(section)
        except Exception as e:
            logger.error(f"Failed to create section: {e}")
            raise

    def update_section(self, section_id: str, name: str) -> Dict[str, Any]:
        """Update a section name"""
        try:
            section = self.api.update_section(section_id=section_id, name=name)

            # Invalidate section cache after update
            if self.cache:
                self.cache.delete_pattern("todoist:sections:*")

            return self._section_to_dict(section)
        except Exception as e:
            logger.error(f"Failed to update section {section_id}: {e}")
            raise

    def delete_section(self, section_id: str) -> bool:
        """Delete a section"""
        try:
            result = self.api.delete_section(section_id)

            # Invalidate caches after deletion
            if self.cache:
                self.cache.delete_pattern("todoist:sections:*")
                self.cache.delete_pattern("todoist:tasks:*")

            return result
        except Exception as e:
            logger.error(f"Failed to delete section {section_id}: {e}")
            raise

    # ========== LABEL OPERATIONS ==========

    @cache_aside(CacheConfig(ttl=CacheTTL.TODOIST_LABELS, key_prefix="todoist:labels"))
    def get_labels(self) -> List[Dict[str, Any]]:
        """Get all labels"""
        try:
            labels_paginator = self.api.get_labels()
            # The paginator returns lists of labels, we need to flatten it
            all_labels: List[Label] = []
            for label_batch in labels_paginator:
                if isinstance(label_batch, list):
                    all_labels.extend(label_batch)
                else:
                    all_labels.append(label_batch)
            return [self._label_to_dict(label) for label in all_labels]
        except Exception as e:
            logger.error(f"Failed to get labels: {e}")
            raise

    def get_label(self, label_id: str) -> Dict[str, Any]:
        """Get a specific label"""
        try:
            label = self.api.get_label(label_id)
            return self._label_to_dict(label)
        except Exception as e:
            logger.error(f"Failed to get label {label_id}: {e}")
            raise

    def create_label(
        self,
        name: str,
        order: Optional[int] = None,
        color: Optional[str] = None,
        is_favorite: bool = False,
    ) -> Dict[str, Any]:
        """Create a new label"""
        # Validate parameters
        self._validate_color(color)

        try:
            label = self.api.add_label(
                name=name, order=order, color=color, is_favorite=is_favorite
            )

            # Invalidate label cache after creation
            if self.cache:
                self.cache.delete_pattern("todoist:labels:*")

            return self._label_to_dict(label)
        except Exception as e:
            logger.error(f"Failed to create label: {e}")
            raise

    def update_label(
        self,
        label_id: str,
        name: Optional[str] = None,
        order: Optional[int] = None,
        color: Optional[str] = None,
        is_favorite: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Update a label"""
        # Validate parameters
        self._validate_color(color)

        try:
            label = self.api.update_label(
                label_id=label_id,
                name=name,
                order=order,
                color=color,
                is_favorite=is_favorite,
            )

            # Invalidate label cache after update
            if self.cache:
                self.cache.delete_pattern("todoist:labels:*")

            return self._label_to_dict(label)
        except Exception as e:
            logger.error(f"Failed to update label {label_id}: {e}")
            raise

    def delete_label(self, label_id: str) -> bool:
        """Delete a label"""
        try:
            result = self.api.delete_label(label_id)

            # Invalidate caches after deletion
            if self.cache:
                self.cache.delete_pattern("todoist:labels:*")
                self.cache.delete_pattern("todoist:tasks:*")

            return result
        except Exception as e:
            logger.error(f"Failed to delete label {label_id}: {e}")
            raise

    def get_shared_labels(self) -> List[str]:
        """Get all shared labels (labels used across shared projects)"""
        try:
            return list(self.api.get_shared_labels())
        except Exception as e:
            logger.error(f"Failed to get shared labels: {e}")
            raise

    def rename_shared_label(self, old_name: str, new_name: str) -> bool:
        """Rename a shared label across all shared projects"""
        try:
            result = self.api.rename_shared_label(name=old_name, new_name=new_name)

            # Invalidate caches after rename
            if self.cache:
                self.cache.delete_pattern("todoist:labels:*")
                self.cache.delete_pattern("todoist:tasks:*")

            return result
        except Exception as e:
            logger.error(f"Failed to rename shared label '{old_name}': {e}")
            raise

    def remove_shared_label(self, name: str) -> bool:
        """Remove a shared label from all shared projects"""
        try:
            result = self.api.remove_shared_label(name=name)

            # Invalidate caches after removal
            if self.cache:
                self.cache.delete_pattern("todoist:labels:*")
                self.cache.delete_pattern("todoist:tasks:*")

            return result
        except Exception as e:
            logger.error(f"Failed to remove shared label '{name}': {e}")
            raise

    # ========== COMMENT OPERATIONS ==========

    def get_comments(
        self, project_id: Optional[str] = None, task_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get comments for a project or task"""
        try:
            comments_paginator = self.api.get_comments(
                project_id=project_id, task_id=task_id
            )
            # The paginator returns lists of comments, we need to flatten it
            all_comments = []
            for comment_batch in comments_paginator:
                if isinstance(comment_batch, list):
                    all_comments.extend(comment_batch)
                else:
                    all_comments.append(comment_batch)
            return [self._comment_to_dict(c) for c in all_comments]
        except Exception as e:
            logger.error(f"Failed to get comments: {e}")
            raise

    def get_comment(self, comment_id: str) -> Dict[str, Any]:
        """Get a specific comment"""
        try:
            comment = self.api.get_comment(comment_id)
            return self._comment_to_dict(comment)
        except Exception as e:
            logger.error(f"Failed to get comment {comment_id}: {e}")
            raise

    def create_comment(
        self,
        content: str,
        task_id: Optional[str] = None,
        project_id: Optional[str] = None,
        attachment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Add a comment to a task or project"""
        try:
            comment = self.api.add_comment(
                content=content,
                task_id=task_id,
                project_id=project_id,
                attachment=attachment,
            )
            return self._comment_to_dict(comment)
        except Exception as e:
            logger.error(f"Failed to create comment: {e}")
            raise

    def update_comment(self, comment_id: str, content: str) -> Dict[str, Any]:
        """Update a comment"""
        try:
            comment = self.api.update_comment(comment_id=comment_id, content=content)
            return self._comment_to_dict(comment)
        except Exception as e:
            logger.error(f"Failed to update comment {comment_id}: {e}")
            raise

    def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment"""
        try:
            return self.api.delete_comment(comment_id)
        except Exception as e:
            logger.error(f"Failed to delete comment {comment_id}: {e}")
            raise

    # ========== HELPER METHODS ==========

    def _extract_deadline_from_description(self, description: str) -> Optional[str]:
        """
        Extract deadline date from description field.
        Looks for pattern: [DEADLINE: YYYY-MM-DD]
        """
        if not description:
            return None

        import re

        pattern = r"\[DEADLINE:\s*(\d{4}-\d{2}-\d{2})\]"
        match = re.search(pattern, description)
        if match:
            return match.group(1)
        return None

    def _add_deadline_to_description(self, description: str, deadline: str) -> str:
        """
        Add or update deadline in description field.
        Format: [DEADLINE: YYYY-MM-DD]
        """
        import re

        # Remove existing deadline if present
        pattern = r"\[DEADLINE:\s*\d{4}-\d{2}-\d{2}\]"
        cleaned = re.sub(pattern, "", description or "").strip()

        # Add new deadline
        deadline_tag = f"[DEADLINE: {deadline}]"
        if cleaned:
            return f"{cleaned}\n{deadline_tag}"
        return deadline_tag

    def _task_to_dict(self, task: Task) -> Dict[str, Any]:
        """Convert Task object to dictionary with native deadline support"""
        description = getattr(task, "description", "")
        result = {
            "id": task.id,
            "content": task.content,
            "description": description,
            "is_completed": task.is_completed,
            "labels": getattr(task, "labels", []),
            "priority": task.priority,
            "comment_count": getattr(task, "comment_count", 0),
            "created_at": getattr(task, "created_at", None),
            "creator_id": getattr(task, "creator_id", None),
            "assignee_id": getattr(task, "assignee_id", None),
            "assigner_id": getattr(task, "assigner_id", None),
            "project_id": task.project_id,
            "section_id": getattr(task, "section_id", None),
            "parent_id": getattr(task, "parent_id", None),
            "order": getattr(task, "order", 0),
            "url": getattr(task, "url", None),
        }

        # Handle NATIVE deadline field
        if hasattr(task, "deadline") and task.deadline:
            result["deadline"] = {
                "date": getattr(task.deadline, "date", None),
                "lang": getattr(task.deadline, "lang", None),
            }
            result["deadline_date"] = result["deadline"]["date"]
            result["has_deadline"] = True
        else:
            result["deadline"] = None
            result["deadline_date"] = None
            result["has_deadline"] = False

        if task.due:
            result["due"] = {
                "date": getattr(task.due, "date", None),
                "string": getattr(task.due, "string", None),
                "datetime": getattr(task.due, "datetime", None),
                "timezone": getattr(task.due, "timezone", None),
                "is_recurring": getattr(task.due, "is_recurring", False),
            }
            # Add semantic interpretation
            result["start_date"] = result["due"]["date"]  # Due date = when to start
        else:
            result["due"] = None
            result["start_date"] = None

        if hasattr(task, "duration") and task.duration:
            result["duration"] = {
                "amount": task.duration.amount,
                "unit": task.duration.unit,
            }
        else:
            result["duration"] = None

        return result

    def _project_to_dict(self, project: Project) -> Dict[str, Any]:
        """Convert Project object to dictionary"""
        return {
            "id": project.id,
            "name": project.name,
            "color": project.color,
            "parent_id": project.parent_id,
            "order": project.order,
            "is_shared": project.is_shared,
            "is_favorite": project.is_favorite,
            "is_inbox_project": project.is_inbox_project,
            "is_archived": getattr(project, "is_archived", False),
            "is_collapsed": getattr(project, "is_collapsed", False),
            "view_style": project.view_style,
            "url": project.url,
            "description": getattr(project, "description", ""),
            "workspace_id": getattr(project, "workspace_id", None),
            "folder_id": getattr(project, "folder_id", None),
        }

    def _section_to_dict(self, section: Section) -> Dict[str, Any]:
        """Convert Section object to dictionary"""
        return {
            "id": section.id,
            "name": section.name,
            "project_id": section.project_id,
            "order": section.order,
        }

    def _label_to_dict(self, label: Label) -> Dict[str, Any]:
        """Convert Label object to dictionary"""
        return {
            "id": label.id,
            "name": label.name,
            "color": label.color,
            "order": label.order,
            "is_favorite": label.is_favorite,
        }

    def _comment_to_dict(self, comment: Comment) -> Dict[str, Any]:
        """Convert Comment object to dictionary"""
        result = {
            "id": comment.id,
            "content": comment.content,
            "posted_at": comment.posted_at,
            "task_id": comment.task_id,
            "project_id": comment.project_id,
        }

        if hasattr(comment, "attachment") and comment.attachment:
            result["attachment"] = {
                "file_name": comment.attachment.file_name,
                "file_type": comment.attachment.file_type,
                "file_url": comment.attachment.file_url,
                "resource_type": comment.attachment.resource_type,
            }
        else:
            result["attachment"] = None

        return result

    # ========== MCP WRAPPER METHODS ==========
    # These methods handle type conversion for MCP tools which pass all parameters as strings

    def create_task_for_mcp(
        self,
        content: str,
        description: Optional[str] = None,
        deadline: Optional[str] = None,  # Maps to deadline_date
        deadline_lang: Optional[str] = None,
        project_id: Optional[str] = None,
        section_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        order: Optional[str] = None,
        labels: Optional[List[str]] = None,
        priority: Optional[str] = None,  # MCP passes as string
        due_string: Optional[str] = None,
        due_date: Optional[str] = None,
        due_datetime: Optional[str] = None,
        due_lang: Optional[str] = None,
        assignee_id: Optional[str] = None,
        duration: Optional[str] = None,  # MCP passes as string
        duration_unit: Optional[str] = None,
    ) -> Dict[str, Any]:
        """MCP wrapper for create_task that handles type conversion"""
        # Convert string parameters to appropriate types
        if order is not None:
            try:
                order = int(order)
            except (ValueError, TypeError):
                order = None

        if priority is not None:
            try:
                priority = int(priority)
            except (ValueError, TypeError):
                pass  # Let validation handle the error

        if duration is not None:
            try:
                duration = int(duration)
            except (ValueError, TypeError):
                duration = None

        return self.create_task(
            content=content,
            description=description,
            deadline_date=deadline,  # Pass deadline to native field
            deadline_lang=deadline_lang,
            project_id=project_id,
            section_id=section_id,
            parent_id=parent_id,
            order=order,
            labels=labels,
            priority=priority,
            due_string=due_string,
            due_date=due_date,
            due_datetime=due_datetime,
            due_lang=due_lang,
            assignee_id=assignee_id,
            duration=duration,
            duration_unit=duration_unit,
        )

    def update_task_for_mcp(
        self,
        task_id: str,
        content: Optional[str] = None,
        description: Optional[str] = None,
        deadline: Optional[str] = None,  # Maps to deadline_date
        deadline_lang: Optional[str] = None,
        labels: Optional[List[str]] = None,
        priority: Optional[str] = None,  # MCP passes as string
        due_string: Optional[str] = None,
        due_date: Optional[str] = None,
        due_datetime: Optional[str] = None,
        due_lang: Optional[str] = None,
        assignee_id: Optional[str] = None,
        duration: Optional[str] = None,  # MCP passes as string
        duration_unit: Optional[str] = None,
    ) -> Dict[str, Any]:
        """MCP wrapper for update_task that handles type conversion"""
        # Convert string parameters to appropriate types
        if priority is not None:
            try:
                priority = int(priority)
            except (ValueError, TypeError):
                pass  # Let validation handle the error

        if duration is not None:
            try:
                duration = int(duration)
            except (ValueError, TypeError):
                duration = None

        return self.update_task(
            task_id=task_id,
            content=content,
            description=description,
            deadline_date=deadline,  # Pass deadline to native field
            deadline_lang=deadline_lang,
            labels=labels,
            priority=priority,
            due_string=due_string,
            due_date=due_date,
            due_datetime=due_datetime,
            due_lang=due_lang,
            assignee_id=assignee_id,
            duration=duration,
            duration_unit=duration_unit,
        )

    def _register_mcp_tools(self):
        """Register MCP tools for this service"""
        # NOTE: Getter tools commented out - use resources instead for read-only data
        # Resources provide: projects, labels, tasks/today, tasks/overdue
        # Commented tools: todoist_get_tasks, todoist_get_projects, todoist_get_labels

        # Task tools
        # Commented out - use resources instead for read-only data
        # self.mcp.tool(
        #     name="todoist_get_tasks",
        #     description="Retrieve tasks from Todoist with optional filtering. Parameters: project_id (filter by project), label_id (filter by label), filter_string (Todoist filter syntax), max_items (limit results, default 100). Returns: Array of task objects with id, content, due date, priority, labels, and project info. Use to: Get active tasks, check due dates, find specific tasks, or list tasks by project/label.",
        #     annotations={"title": "Get Todoist Tasks"}
        # )(self.get_tasks_for_mcp)

        self.mcp.tool(
            name="create_todoist_task",
            description="""Create a new task in Todoist.

## Date Semantics - NOW WITH NATIVE DEADLINE SUPPORT!
✅ Todoist API has BOTH 'due' AND 'deadline' fields:
• **due_date/due_string** → When to START working on the task
• **deadline** → Drop-dead completion date (NATIVE FIELD)

### Examples:
• **Short task**: "Review PR" with due_date="2024-01-15" (do it on this day)
• **Long task**: "School project" with:
  - due_date="2024-01-10" (start working)
  - deadline="2024-01-20" (must complete by)

## Parameters
• content: Task text (required)
• due_string: Natural language for when to START task (optional)
  - Examples: 'tomorrow', 'next Monday', 'Jan 15'
  - This is when you should BEGIN working
• due_date: YYYY-MM-DD when to START task (optional)
• deadline: YYYY-MM-DD drop-dead completion date (optional)
  - Uses NATIVE Todoist deadline field
• deadline_lang: Language for deadline parsing (optional)
• priority: 1-4, where 4 is highest (optional)
• project_id: Project ID (optional)
• labels: Array of label names (optional)
• description: Task details (optional)

## Returns
Created task object with all properties

## Use Cases
• Short tasks: Set due_date for when to do it
• Long projects: Set due_date for start, add [DEADLINE: date] in description
• For reminders: Must be set in Todoist app (API limitation)""",
            title="Create Todoist Task",
            annotations={"title": "Create Todoist Task"},
        )(self.create_task_for_mcp)

        self.mcp.tool(
            name="update_todoist_task",
            description="""Update an existing Todoist task.

## Date Semantics - NOW WITH NATIVE DEADLINE SUPPORT!
✅ Todoist API has BOTH 'due' AND 'deadline' fields:
• **due_date/due_string** → When to START working on the task
• **deadline** → Drop-dead completion date (NATIVE FIELD)

## Parameters
• task_id: Task ID to update (required)
• content: New task text (optional)
• due_string: Natural language for when to START task (optional)
  - This is when you should BEGIN working
  - Examples: 'tomorrow', 'next Monday'
• due_date: YYYY-MM-DD when to START task (optional)
• deadline: YYYY-MM-DD drop-dead completion date (optional)
  - Uses NATIVE Todoist deadline field
• deadline_lang: Language for deadline parsing (optional)
• priority: 1-4, where 4 is highest (optional)
• labels: Array of label names (optional)
• description: New description (optional)

## Returns
Updated task object

## Use Cases
• Reschedule when to START working on tasks
• Add or update DEADLINE in description
• Change task priorities or labels
• Update both start date and deadline independently""",
            title="Update Todoist Task",
            annotations={"title": "Update Todoist Task"},
        )(self.update_task_for_mcp)

        self.mcp.tool(
            name="complete_todoist_task",
            description="""Mark a Todoist task as completed.

## Parameters
• task_id: Task ID to complete (required)
  - Get from task queries or previous responses

## Returns
Success/error status

## Use Cases
• Mark finished tasks as done
• Complete tasks from today's list
• Clear completed items

## Related Tools
• Use `reopen_todoist_task` if completed by mistake""",
            title="Complete Todoist Task",
            annotations={"title": "Complete Todoist Task"},
        )(self.close_task_for_mcp)

        self.mcp.tool(
            name="reopen_todoist_task",
            description="""Reopen a previously completed Todoist task.

## Parameters
• task_id: Task ID to reopen (required)
  - Get from completed task history

## Returns
Success/error status

## Use Cases
• Restore tasks completed by mistake
• Reactivate recurring tasks
• Redo completed tasks""",
            title="Reopen Todoist Task",
            annotations={"title": "Reopen Todoist Task"},
        )(self.reopen_task_for_mcp)

        self.mcp.tool(
            name="delete_todoist_task",
            description="""Permanently delete a Todoist task.

## Parameters
• task_id: Task ID to delete (required)
  - Get from task queries or previous responses

## Returns
Success/error status

## Use Cases
• Remove irrelevant tasks
• Delete tasks created by mistake
• Clean up old or cancelled tasks

⚠️ **Warning**: This is permanent and cannot be undone""",
            title="Delete Todoist Task",
            annotations={"title": "Delete Todoist Task"},
        )(self.delete_task_for_mcp)

        self.mcp.tool(
            name="move_todoist_task",
            description="""Move a task to a different project, section, or make it a subtask.

## Parameters (specify exactly ONE)
• task_id: Task ID to move (required)
• project_id: Target project ID - moves task to project root (optional)
  - Call `get_todoist_projects` to see available projects
• section_id: Target section ID - moves task to section (optional)
  - Sections are within projects
• parent_id: Target parent task ID - makes this a subtask (optional)

## Important
Only ONE of project_id, section_id, or parent_id can be specified.
To move from a section back to project root, use project_id.

## Returns
Updated task object with new location

## Use Cases
• Reorganize tasks between projects
• Move tasks into sections for better organization
• Create task hierarchies with subtasks
• Move tasks out of sections to project root""",
            title="Move Todoist Task",
            annotations={"title": "Move Todoist Task"},
        )(self.move_task_for_mcp)

        self.mcp.tool(
            name="quick_add_todoist_task",
            description="""Create a task using Todoist's Quick Add natural language syntax.

## Parameters
• text: Quick add text (required)
  - Supports natural language dates, projects, labels, priorities

## Syntax Examples
• "Buy milk tomorrow p1 #Shopping @errands"
• "Meeting with John every Monday at 10am"
• "Submit report by Friday #Work"
• "Call mom p2 @phone"
• "Review PR today #dev @work"

## Syntax Guide
• Dates: tomorrow, next Monday, Jan 15, every week
• Priority: p1, p2, p3, p4 (p1 is highest)
• Project: #ProjectName
• Labels: @label1 @label2
• Time: at 10am, at 2:30pm

## Returns
Created task object with parsed properties

## Use Cases
• Fast task entry with natural language
• Creating recurring tasks easily
• Quick capture without separate fields""",
            title="Quick Add Todoist Task",
            annotations={"title": "Quick Add Todoist Task"},
        )(self.quick_add_task)

        self.mcp.tool(
            name="get_todoist_completed_tasks",
            description="""Get completed tasks by completion date.

## Parameters
• project_id: Filter by project (optional)
• section_id: Filter by section (optional)
• limit: Max results, default 50 (optional)

## Returns
• items: List of completed tasks
• has_more: Whether more results exist
• cursor: Pagination cursor for next page

## Use Cases
• Review completed work
• Track productivity
• Find recently finished tasks""",
            title="Get Completed Tasks",
            annotations={"title": "Get Completed Tasks"},
        )(self.get_completed_tasks)

        self.mcp.tool(
            name="get_todoist_completed_by_due_date",
            description="""Get completed tasks that were due on a specific date.

## Parameters
• due_date: Date in YYYY-MM-DD format (required)
• project_id: Filter by project (optional)
• limit: Max results, default 50 (optional)

## Returns
• items: List of completed tasks due on that date
• has_more: Whether more results exist

## Use Cases
• See what was accomplished on a specific day
• Review tasks completed for a deadline
• Historical task analysis""",
            title="Get Completed Tasks by Due Date",
            annotations={"title": "Get Completed Tasks by Due Date"},
        )(self.get_completed_tasks_by_due_date)

        # Project tools
        # Commented out - use resources instead for read-only data
        # self.mcp.tool(
        #     name="todoist_get_projects",
        #     description="Retrieve all projects from Todoist account. No parameters required. Returns: Array of project objects with id, name, color, parent_id, order, and other properties. Use to: See available projects for task organization and management.",
        #     annotations={"title": "Get Todoist Projects"}
        # )(self.get_projects_for_mcp)

        self.mcp.tool(
            name="create_todoist_project",
            description="""Create a new project or sub-project in Todoist.

## Parameters
• name: Project name (required)
• parent_id: Parent project ID to create a sub-project (optional)
  - Call `get_todoist_projects` to see available parent projects
  - Sub-projects appear nested under their parent
  - Sub-projects inherit some parent settings
• color: Project color (optional)
  - Call `get_todoist_colors` to see available colors
• is_favorite: Mark as favorite (boolean, optional)
• view_style: 'list' or 'board' view (optional)

## Returns
Created project object with all properties including parent_id

## Use Cases
• Create top-level projects for major areas (Work, Personal, etc.)
• Create sub-projects for categories within a parent project
• Build project hierarchies for complex organization

## Examples
• Top-level: name="Work" (no parent_id)
• Sub-project: name="Q1 Goals", parent_id="<work_project_id>"
• Nested: name="Marketing", parent_id="<q1_goals_id>"

⚠️ **Note**: Once created, a project's parent cannot be changed via the API""",
            title="Create Todoist Project",
            annotations={"title": "Create Todoist Project"},
        )(self.create_project)

        self.mcp.tool(
            name="update_todoist_project",
            description="""Update an existing project in Todoist.

## Parameters
• project_id: Project ID to update (required)
  - Call `get_todoist_projects` to see available project IDs
• name: New project name (optional)
• color: New project color (optional)
  - Call `get_todoist_colors` to see available colors
• is_favorite: Mark as favorite (boolean, optional)
• view_style: 'list' or 'board' view (optional)

## Returns
Updated project object with all properties

## Use Cases
• Rename existing projects
• Change project color for better organization
• Toggle favorite status
• Switch between list and board views

⚠️ **Limitation**: Cannot change project's parent (move sub-project).
The parent_id is set at creation and cannot be modified via API.""",
            title="Update Todoist Project",
            annotations={"title": "Update Todoist Project"},
        )(self.update_project)

        self.mcp.tool(
            name="delete_todoist_project",
            description="""Permanently delete a project and all its tasks.

## Parameters
• project_id: Project ID to delete (required)
  - Call `get_todoist_projects` to see available project IDs

## Returns
Success/error status

## Use Cases
• Remove unused projects
• Clean up test projects
• Delete completed project areas

⚠️ **Warning**: This permanently deletes the project AND all tasks within it.
This action cannot be undone.""",
            title="Delete Todoist Project",
            annotations={"title": "Delete Todoist Project"},
        )(self.delete_project_for_mcp)

        self.mcp.tool(
            name="archive_todoist_project",
            description="""Archive a project (hide without deleting).

## Parameters
• project_id: Project ID to archive (required)
  - Call `get_todoist_projects` to see available project IDs

## Returns
Success/error status

## Use Cases
• Hide completed projects
• Temporarily remove projects from view
• Preserve project data while decluttering

## Notes
• Archived projects can be restored with unarchive_todoist_project
• Tasks remain intact but hidden""",
            title="Archive Todoist Project",
            annotations={"title": "Archive Todoist Project"},
        )(self.archive_project_for_mcp)

        self.mcp.tool(
            name="unarchive_todoist_project",
            description="""Restore an archived project.

## Parameters
• project_id: Project ID to unarchive (required)

## Returns
Success/error status

## Use Cases
• Restore accidentally archived projects
• Reactivate old projects
• Bring back completed projects for reference""",
            title="Unarchive Todoist Project",
            annotations={"title": "Unarchive Todoist Project"},
        )(self.unarchive_project_for_mcp)

        self.mcp.tool(
            name="get_todoist_collaborators",
            description="""Get collaborators for a shared project.

## Parameters
• project_id: Shared project ID (required)
  - Call `get_todoist_projects` to see available project IDs

## Returns
List of collaborators with:
• id: Collaborator user ID
• name: Display name
• email: Email address

## Use Cases
• See who has access to a project
• Get user IDs for task assignment
• Review project sharing""",
            title="Get Project Collaborators",
            annotations={"title": "Get Project Collaborators"},
        )(self.get_collaborators)

        # Label tools
        # Commented out - use resources instead for read-only data
        # self.mcp.tool(
        #     name="todoist_get_labels",
        #     description="Retrieve all labels from Todoist account. No parameters required. Returns: Array of label objects with id, name, color, order, and favorite status. Use to: See available labels for task categorization and filtering.",
        #     annotations={"title": "Get Todoist Labels"}
        # )(self.get_labels_for_mcp)

        self.mcp.tool(
            name="create_todoist_label",
            description="""Create a new label in Todoist.

## Parameters
• name: Label name (required)
• color: Label color (optional)
  - Call `get_todoist_colors` to see available colors
• is_favorite: Mark as favorite (boolean, optional)

## Returns
Created label object with all properties

## Use Cases
• Add new task categories
• Create context tags
• Organize by themes or topics""",
            title="Create Todoist Label",
            annotations={"title": "Create Todoist Label"},
        )(self.create_label)

        self.mcp.tool(
            name="update_todoist_label",
            description="""Update an existing label in Todoist.

## Parameters
• label_id: Label ID to update (required)
  - Call `get_todoist_labels` to see available label IDs
• name: New label name (optional)
• color: New label color (optional)
  - Call `get_todoist_colors` to see available colors
• is_favorite: Mark as favorite (boolean, optional)

## Returns
Updated label object with all properties

## Use Cases
• Rename existing labels
• Change label color
• Toggle favorite status""",
            title="Update Todoist Label",
            annotations={"title": "Update Todoist Label"},
        )(self.update_label_for_mcp)

        self.mcp.tool(
            name="delete_todoist_label",
            description="""Delete a label from Todoist.

## Parameters
• label_id: Label ID to delete (required)
  - Call `get_todoist_labels` to see available label IDs

## Returns
Success/error status

## Use Cases
• Remove unused labels
• Clean up label organization

⚠️ **Note**: This removes the label from all tasks that use it.""",
            title="Delete Todoist Label",
            annotations={"title": "Delete Todoist Label"},
        )(self.delete_label_for_mcp)

        self.mcp.tool(
            name="get_todoist_shared_labels",
            description="""Get all shared labels (labels used in shared projects).

## Returns
List of shared label names

## Use Cases
• See labels available across shared projects
• Coordinate labeling with collaborators""",
            title="Get Shared Labels",
            annotations={"title": "Get Shared Labels"},
        )(self.get_shared_labels_for_mcp)

        self.mcp.tool(
            name="rename_todoist_shared_label",
            description="""Rename a shared label across all shared projects.

## Parameters
• old_name: Current label name (required)
• new_name: New label name (required)

## Returns
Success/error status

## Use Cases
• Standardize label names across projects
• Fix label typos in shared projects""",
            title="Rename Shared Label",
            annotations={"title": "Rename Shared Label"},
        )(self.rename_shared_label_for_mcp)

        self.mcp.tool(
            name="remove_todoist_shared_label",
            description="""Remove a shared label from all shared projects.

## Parameters
• name: Shared label name to remove (required)

## Returns
Success/error status

## Use Cases
• Clean up shared labels
• Remove deprecated labels from shared projects""",
            title="Remove Shared Label",
            annotations={"title": "Remove Shared Label"},
        )(self.remove_shared_label_for_mcp)

        # Section tools
        self.mcp.tool(
            name="get_todoist_sections",
            description=f"""Get sections, optionally filtered by project (cached for {CacheTTL.TODOIST_SECTIONS//60} minutes).

## Parameters
• project_id: Filter by project (optional)
  - Call `get_todoist_projects` to see available project IDs

## Returns
List of sections with:
• id: Section ID
• name: Section name
• project_id: Parent project
• order: Sort order

## Use Cases
• See available sections for task organization
• Get section IDs for moving tasks
• Understand project structure""",
            title="Get Todoist Sections",
            annotations={"title": "Get Todoist Sections"},
        )(self.get_sections_for_mcp)

        self.mcp.tool(
            name="create_todoist_section",
            description="""Create a new section in a project.

## Parameters
• name: Section name (required)
• project_id: Project to create section in (required)
  - Call `get_todoist_projects` to see available project IDs
• order: Position in section list (optional)

## Returns
Created section object

## Use Cases
• Organize tasks within projects
• Create workflow stages (To Do, In Progress, Done)
• Group related tasks""",
            title="Create Todoist Section",
            annotations={"title": "Create Todoist Section"},
        )(self.create_section_for_mcp)

        self.mcp.tool(
            name="update_todoist_section",
            description="""Update a section name.

## Parameters
• section_id: Section ID to update (required)
  - Call `get_todoist_sections` to see available section IDs
• name: New section name (required)

## Returns
Updated section object

## Use Cases
• Rename sections
• Fix typos in section names""",
            title="Update Todoist Section",
            annotations={"title": "Update Todoist Section"},
        )(self.update_section_for_mcp)

        self.mcp.tool(
            name="delete_todoist_section",
            description="""Delete a section from a project.

## Parameters
• section_id: Section ID to delete (required)
  - Call `get_todoist_sections` to see available section IDs

## Returns
Success/error status

## Use Cases
• Remove unused sections
• Simplify project structure

⚠️ **Note**: Tasks in the section will be moved to the project root, not deleted.""",
            title="Delete Todoist Section",
            annotations={"title": "Delete Todoist Section"},
        )(self.delete_section_for_mcp)

        # Comment tools
        self.mcp.tool(
            name="get_todoist_comments",
            description="""Get comments for a task or project.

## Parameters (specify one)
• task_id: Get comments on a task (optional)
• project_id: Get comments on a project (optional)

## Returns
List of comments with:
• id: Comment ID
• content: Comment text
• posted_at: Timestamp
• attachment: File attachment info (if any)

## Use Cases
• Read task discussions
• Review project notes
• Get context on tasks""",
            title="Get Todoist Comments",
            annotations={"title": "Get Todoist Comments"},
        )(self.get_comments_for_mcp)

        self.mcp.tool(
            name="create_todoist_comment",
            description="""Add a comment to a task or project.

## Parameters
• content: Comment text (required)
• task_id: Add comment to task (optional)
• project_id: Add comment to project (optional)

Note: Specify either task_id OR project_id, not both.

## Returns
Created comment object

## Use Cases
• Add notes to tasks
• Document decisions
• Communicate with collaborators""",
            title="Create Todoist Comment",
            annotations={"title": "Create Todoist Comment"},
        )(self.create_comment_for_mcp)

        self.mcp.tool(
            name="update_todoist_comment",
            description="""Update a comment's content.

## Parameters
• comment_id: Comment ID to update (required)
• content: New comment text (required)

## Returns
Updated comment object

## Use Cases
• Fix typos in comments
• Update outdated information
• Clarify previous notes""",
            title="Update Todoist Comment",
            annotations={"title": "Update Todoist Comment"},
        )(self.update_comment_for_mcp)

        self.mcp.tool(
            name="delete_todoist_comment",
            description="""Delete a comment.

## Parameters
• comment_id: Comment ID to delete (required)

## Returns
Success/error status

## Use Cases
• Remove outdated comments
• Delete accidental comments""",
            title="Delete Todoist Comment",
            annotations={"title": "Delete Todoist Comment"},
        )(self.delete_comment_for_mcp)

        # Register tools (Claude cannot use resources, only tools)
        self.mcp.tool(
            name="get_todoist_projects",
            description=f"""Get all Todoist projects with their details (cached for {CacheTTL.TODOIST_PROJECTS//60} minutes).

## Returns
• Project IDs and names
• Project colors
• Parent-child hierarchy
• Order and favorite status

## Use Cases
• See available projects for task creation
• Get project IDs for other tools
• Understand project organization

## Caching
• Project list cached for {CacheTTL.TODOIST_PROJECTS//60} minutes
• Projects change infrequently, reducing API calls""",
            title="Todoist Projects",
            annotations={"title": "Todoist Projects"},
        )(self.get_projects_resource)

        self.mcp.tool(
            name="get_todoist_labels",
            description=f"""Get all Todoist labels for task categorization (cached for {CacheTTL.TODOIST_LABELS//60} minutes).

## Returns
• Label names and IDs
• Label colors
• Favorite status

## Use Cases
• See available labels for task creation
• Get label names for filtering
• Understand categorization options

## Caching
• Label list cached for {CacheTTL.TODOIST_LABELS//60} minutes
• Labels rarely change, optimizing performance""",
            title="Todoist Labels",
            annotations={"title": "Todoist Labels"},
        )(self.get_labels_resource)

        self.mcp.tool(
            name="get_todoist_tasks_today",
            description=f"""Get all Todoist tasks due today (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Returns
• Tasks due today
• Task IDs and content
• Priority levels
• Project and label information

## Use Cases
• Daily task overview
• Today's priorities
• Current workload check

## Related Tools
• Use `get_todoist_all_due_today` to include overdue tasks
• Use `get_todoist_tasks_overdue` for overdue only

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Short cache ensures fresh task status""",
            title="Today's Tasks",
            annotations={"title": "Today's Tasks"},
        )(self.get_today_tasks_resource)

        self.mcp.tool(
            name="get_todoist_tasks_overdue",
            description=f"""Get all overdue Todoist tasks that need attention (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Returns
• Overdue tasks
• How many days overdue
• Task priorities
• Project information

## Use Cases
• Catch up on missed tasks
• Prioritize overdue work
• Reschedule old tasks

## Related Tools
• Use `update_todoist_task` to reschedule
• Use `complete_todoist_task` to mark done

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Frequently updated to reflect task changes""",
            title="Overdue Tasks",
            annotations={"title": "Overdue Tasks"},
        )(self.get_overdue_tasks_resource)

        # Parameterized queries as tools (Claude can only get static resources)
        self.mcp.tool(
            name="get_tasks_by_project",
            description=f"""Get all tasks for a specific project (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Parameters
• project_id: Project ID (required)
  - Call `get_todoist_projects` to see available project IDs

## Returns
All tasks in the specified project

## Use Cases
• View project progress
• Get project-specific tasks
• Project management overview

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Project-specific queries use cached task list""",
            title="Get Tasks by Project",
            annotations={"title": "Get Tasks by Project"},
        )(self.get_project_tasks_resource)

        self.mcp.tool(
            name="get_tasks_by_label",
            description=f"""Get all tasks with a specific label (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Parameters
• label_name: Label name (required)
  - Call `get_todoist_labels` to see available labels

## Returns
All tasks with the specified label

## Use Cases
• Filter tasks by context
• Get category-specific tasks
• Review labeled items

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Label-filtered queries use cached task list""",
            title="Get Tasks by Label",
            annotations={"title": "Get Tasks by Label"},
        )(self.get_label_tasks_resource)

        self.mcp.tool(
            name="get_tasks_by_priority",
            description=f"""Get all tasks with a specific priority (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Parameters
• priority: Priority level 1-4, where 4 is highest (required)
  - Call `get_todoist_priorities` to understand priority meanings

## Returns
All tasks with the specified priority

## Use Cases
• Focus on high-priority work
• Review urgent tasks
• Prioritize workload

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Priority filtering on cached data""",
            title="Get Tasks by Priority",
            annotations={"title": "Get Tasks by Priority"},
        )(self.get_priority_tasks_resource)

        self.mcp.tool(
            name="get_tasks_by_filter",
            description=f"""Get tasks matching a Todoist filter query (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Parameters
• filter_string: Todoist filter syntax (required)
  - Call `get_todoist_filters` to see common filter examples
  - Examples: 'today', 'tomorrow', '7 days', 'p1', '@work'

## Returns
Tasks matching the filter criteria

## Use Cases
• Custom task queries
• Complex filtering
• Advanced task searches

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Complex filters applied to cached data""",
            title="Get Tasks by Filter",
            annotations={"title": "Get Tasks by Filter"},
        )(self.get_filtered_tasks_resource)

        self.mcp.tool(
            name="get_project_details",
            description="""Get detailed information about a specific project.

## Parameters
• project_id: Project ID (required)
  - Call `get_todoist_projects` to see available project IDs

## Returns
• Project name and color
• Task count
• Hierarchy information
• View style and settings

## Use Cases
• Project statistics
• Detailed project info
• Project analysis""",
            title="Get Project Details",
            annotations={"title": "Get Project Details"},
        )(self.get_project_details_resource)

        self.mcp.tool(
            name="get_todoist_inbox_tasks",
            description=f"""Get all tasks in the inbox (no project assigned) (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Returns
• Tasks without project assignment
• Task details and priorities
• Due dates and labels

## Use Cases
• Process unorganized tasks
• Triage inbox items
• Assign tasks to projects

## Related Tools
• Use `update_todoist_task` to assign to projects

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Filters for tasks without project""",
            title="Inbox Tasks",
            annotations={"title": "Inbox Tasks"},
        )(self.get_inbox_tasks_resource)

        # Tools for constant values (for LLM discovery)
        self.mcp.tool(
            name="get_todoist_priorities",
            description="""Get available priority levels and their meanings.

## Returns
• Priority levels 1-4
• Color codes for each priority
• Meaning and usage guidelines

## Use Cases
• Understand priority system
• Reference for task creation
• Priority color mapping""",
            title="Priority Levels",
            annotations={"title": "Priority Levels"},
        )(self.get_priorities_resource)

        self.mcp.tool(
            name="get_todoist_colors",
            description="""Get available colors for projects and labels.

## Returns
• Color names and IDs
• Hex color codes
• Usage for projects vs labels

## Use Cases
• Choose colors for new projects
• Select label colors
• Color reference for creation tools""",
            title="Available Colors",
            annotations={"title": "Available Colors"},
        )(self.get_colors_resource)

        self.mcp.tool(
            name="get_todoist_filters",
            description="""Get commonly used Todoist filter strings.

## Returns
• Common filter examples
• Filter syntax explanation
• Advanced filter combinations

## Use Cases
• Learn filter syntax
• Reference for `get_tasks_by_filter`
• Build custom queries""",
            title="Common Filters",
            annotations={"title": "Common Filters"},
        )(self.get_common_filters_resource)

        # Additional tools for common queries
        self.mcp.tool(
            name="get_todoist_all_due_today",
            description=f"""Get all tasks due today plus overdue tasks (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Returns
• Tasks due today
• All overdue tasks
• Combined priority view
• Organized by urgency

## Use Cases
• Complete daily overview
• Catch up on all due work
• Daily planning with backlog

## Related Tools
• Use `get_todoist_tasks_today` for today only
• Use `get_todoist_tasks_overdue` for overdue only

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Combines today and overdue from cache""",
            title="All Due Today",
            annotations={"title": "All Due Today"},
        )(self.get_all_due_today_resource)

        self.mcp.tool(
            name="get_todoist_week_tasks",
            description=f"""Get all tasks due this week (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Returns
• Tasks due this week
• Organized by day
• Priority information

## Use Cases
• Weekly planning
• Week overview
• Workload assessment

## Related Tools
• Use `get_todoist_tasks_today` for today only
• Use `get_tasks_by_filter` with '7 days' for next 7 days

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Filters cached data for current week""",
            title="This Week's Tasks",
            annotations={"title": "This Week's Tasks"},
        )(self.get_week_tasks_resource)

        self.mcp.tool(
            name="get_todoist_high_priority_tasks",
            description=f"""Get all high priority tasks (P1 and P2) (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Returns
• Priority 1 tasks (highest)
• Priority 2 tasks (high)
• Due dates and projects

## Use Cases
• Focus on urgent work
• Priority task review
• Critical task management

## Related Tools
• Use `get_tasks_by_priority` for specific priority level
• Use `get_todoist_priorities` to understand priority system

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Filters for P1 and P2 priorities""",
            title="High Priority Tasks",
            annotations={"title": "High Priority Tasks"},
        )(self.get_high_priority_tasks_resource)

        self.mcp.tool(
            name="get_todoist_no_date_tasks",
            description=f"""Get all tasks that don't have a due date assigned (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Returns
• Tasks without due dates
• Project and label information
• Priority levels

## Use Cases
• Review unscheduled work
• Assign dates to tasks
• Backlog management

## Related Tools
• Use `update_todoist_task` to add due dates

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Filters for tasks with no due date""",
            title="Tasks Without Due Date",
            annotations={"title": "Tasks Without Due Date"},
        )(self.get_no_date_tasks_resource)

        self.mcp.tool(
            name="get_tasks_with_deadlines",
            description="""Get tasks that have deadlines specified in their descriptions.

## How Deadlines Work
Since Todoist only has one 'due' field, we use:
• **due date** = When to START working on the task
• **[DEADLINE: YYYY-MM-DD]** in description = Drop-dead completion date

## Returns
• Tasks with [DEADLINE: date] in description
• Start date (from due field)
• Deadline date (from description)
• Days until deadline
• Warning if deadline is approaching

## Use Cases
• Find all tasks with explicit deadlines
• Check for approaching deadlines
• Review long-term projects
• Identify tasks that need deadline updates""",
            title="Get Tasks with Deadlines",
            annotations={"title": "Get Tasks with Deadlines"},
        )(self.get_tasks_with_deadlines_resource)

        self.mcp.tool(
            name="get_todoist_stats",
            description=f"""Get statistics about your tasks (cached for {CacheTTL.TODOIST_TASKS} seconds).

## Returns
• Total task count
• Tasks by priority
• Tasks by project
• Overdue statistics
• Completion trends

## Use Cases
• Productivity analysis
• Task overview
• Workload assessment

## Caching
• Task data cached for {CacheTTL.TODOIST_TASKS} seconds
• Statistics computed from cached task list""",
            title="Task Statistics",
            annotations={"title": "Task Statistics"},
        )(self.get_task_stats_resource)

    # MCP Tool Wrappers
    def get_tasks_for_mcp(
        self,
        project_id: Optional[str] = None,
        label: Optional[str] = None,
        filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """MCP tool wrapper for get_tasks"""
        try:
            tasks = self.get_tasks(
                project_id=project_id, label=label, filter_str=filter
            )
            return {"tasks": tasks, "count": len(tasks)}
        except Exception as e:
            logger.error(f"Error getting tasks: {e}")
            return {"error": str(e)}

    def close_task_for_mcp(self, task_id: str) -> Dict[str, Any]:
        """MCP tool wrapper for close_task"""
        try:
            result = self.close_task(task_id)
            return {"success": result, "message": f"Task {task_id} completed"}
        except Exception as e:
            logger.error(f"Error closing task: {e}")
            return {"error": str(e)}

    def reopen_task_for_mcp(self, task_id: str) -> Dict[str, Any]:
        """MCP tool wrapper for reopen_task"""
        try:
            result = self.reopen_task(task_id)
            return {"success": result, "message": f"Task {task_id} reopened"}
        except Exception as e:
            logger.error(f"Error reopening task: {e}")
            return {"error": str(e)}

    def delete_task_for_mcp(self, task_id: str) -> Dict[str, Any]:
        """MCP tool wrapper for delete_task"""
        try:
            result = self.delete_task(task_id)
            return {"success": result, "message": f"Task {task_id} deleted"}
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            return {"error": str(e)}

    def move_task_for_mcp(
        self,
        task_id: str,
        project_id: Optional[str] = None,
        section_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """MCP tool wrapper for move_task"""
        try:
            task = self.move_task(
                task_id=task_id,
                project_id=project_id,
                section_id=section_id,
                parent_id=parent_id,
            )
            return {
                "success": True,
                "message": f"Task {task_id} moved successfully",
                "task": task,
            }
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Error moving task: {e}")
            return {"error": str(e)}

    def get_projects_for_mcp(self) -> Dict[str, Any]:
        """MCP tool wrapper for get_projects"""
        try:
            projects = self.get_projects()
            return {"projects": projects, "count": len(projects)}
        except Exception as e:
            logger.error(f"Error getting projects: {e}")
            return {"error": str(e)}

    def get_labels_for_mcp(self) -> Dict[str, Any]:
        """MCP tool wrapper for get_labels"""
        try:
            labels = self.get_labels()
            return {"labels": labels, "count": len(labels)}
        except Exception as e:
            logger.error(f"Error getting labels: {e}")
            return {"error": str(e)}

    # Project MCP Wrappers
    def delete_project_for_mcp(self, project_id: str) -> Dict[str, Any]:
        """MCP tool wrapper for delete_project"""
        try:
            result = self.delete_project(project_id)
            return {"success": result, "message": f"Project {project_id} deleted"}
        except Exception as e:
            logger.error(f"Error deleting project: {e}")
            return {"error": str(e)}

    def archive_project_for_mcp(self, project_id: str) -> Dict[str, Any]:
        """MCP tool wrapper for archive_project"""
        try:
            result = self.archive_project(project_id)
            return {"success": result, "message": f"Project {project_id} archived"}
        except Exception as e:
            logger.error(f"Error archiving project: {e}")
            return {"error": str(e)}

    def unarchive_project_for_mcp(self, project_id: str) -> Dict[str, Any]:
        """MCP tool wrapper for unarchive_project"""
        try:
            result = self.unarchive_project(project_id)
            return {"success": result, "message": f"Project {project_id} unarchived"}
        except Exception as e:
            logger.error(f"Error unarchiving project: {e}")
            return {"error": str(e)}

    # Section MCP Wrappers
    def get_sections_for_mcp(
        self, project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """MCP tool wrapper for get_sections"""
        try:
            sections = self.get_sections(project_id=project_id)
            return {"sections": sections, "count": len(sections)}
        except Exception as e:
            logger.error(f"Error getting sections: {e}")
            return {"error": str(e)}

    def create_section_for_mcp(
        self, name: str, project_id: str, order: Optional[int] = None
    ) -> Dict[str, Any]:
        """MCP tool wrapper for create_section"""
        try:
            section = self.create_section(name=name, project_id=project_id, order=order)
            return {"success": True, "section": section}
        except Exception as e:
            logger.error(f"Error creating section: {e}")
            return {"error": str(e)}

    def update_section_for_mcp(self, section_id: str, name: str) -> Dict[str, Any]:
        """MCP tool wrapper for update_section"""
        try:
            section = self.update_section(section_id=section_id, name=name)
            return {"success": True, "section": section}
        except Exception as e:
            logger.error(f"Error updating section: {e}")
            return {"error": str(e)}

    def delete_section_for_mcp(self, section_id: str) -> Dict[str, Any]:
        """MCP tool wrapper for delete_section"""
        try:
            result = self.delete_section(section_id)
            return {"success": result, "message": f"Section {section_id} deleted"}
        except Exception as e:
            logger.error(f"Error deleting section: {e}")
            return {"error": str(e)}

    # Label MCP Wrappers
    def update_label_for_mcp(
        self,
        label_id: str,
        name: Optional[str] = None,
        color: Optional[str] = None,
        is_favorite: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """MCP tool wrapper for update_label"""
        try:
            label = self.update_label(
                label_id=label_id, name=name, color=color, is_favorite=is_favorite
            )
            return {"success": True, "label": label}
        except Exception as e:
            logger.error(f"Error updating label: {e}")
            return {"error": str(e)}

    def delete_label_for_mcp(self, label_id: str) -> Dict[str, Any]:
        """MCP tool wrapper for delete_label"""
        try:
            result = self.delete_label(label_id)
            return {"success": result, "message": f"Label {label_id} deleted"}
        except Exception as e:
            logger.error(f"Error deleting label: {e}")
            return {"error": str(e)}

    def get_shared_labels_for_mcp(self) -> Dict[str, Any]:
        """MCP tool wrapper for get_shared_labels"""
        try:
            labels = self.get_shared_labels()
            return {"shared_labels": labels, "count": len(labels)}
        except Exception as e:
            logger.error(f"Error getting shared labels: {e}")
            return {"error": str(e)}

    def rename_shared_label_for_mcp(
        self, old_name: str, new_name: str
    ) -> Dict[str, Any]:
        """MCP tool wrapper for rename_shared_label"""
        try:
            result = self.rename_shared_label(old_name=old_name, new_name=new_name)
            return {
                "success": result,
                "message": f"Shared label '{old_name}' renamed to '{new_name}'",
            }
        except Exception as e:
            logger.error(f"Error renaming shared label: {e}")
            return {"error": str(e)}

    def remove_shared_label_for_mcp(self, name: str) -> Dict[str, Any]:
        """MCP tool wrapper for remove_shared_label"""
        try:
            result = self.remove_shared_label(name=name)
            return {"success": result, "message": f"Shared label '{name}' removed"}
        except Exception as e:
            logger.error(f"Error removing shared label: {e}")
            return {"error": str(e)}

    # Comment MCP Wrappers
    def get_comments_for_mcp(
        self, task_id: Optional[str] = None, project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """MCP tool wrapper for get_comments"""
        try:
            comments = self.get_comments(task_id=task_id, project_id=project_id)
            return {"comments": comments, "count": len(comments)}
        except Exception as e:
            logger.error(f"Error getting comments: {e}")
            return {"error": str(e)}

    def create_comment_for_mcp(
        self,
        content: str,
        task_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """MCP tool wrapper for create_comment"""
        try:
            comment = self.create_comment(
                content=content, task_id=task_id, project_id=project_id
            )
            return {"success": True, "comment": comment}
        except Exception as e:
            logger.error(f"Error creating comment: {e}")
            return {"error": str(e)}

    def update_comment_for_mcp(
        self, comment_id: str, content: str
    ) -> Dict[str, Any]:
        """MCP tool wrapper for update_comment"""
        try:
            comment = self.update_comment(comment_id=comment_id, content=content)
            return {"success": True, "comment": comment}
        except Exception as e:
            logger.error(f"Error updating comment: {e}")
            return {"error": str(e)}

    def delete_comment_for_mcp(self, comment_id: str) -> Dict[str, Any]:
        """MCP tool wrapper for delete_comment"""
        try:
            result = self.delete_comment(comment_id)
            return {"success": result, "message": f"Comment {comment_id} deleted"}
        except Exception as e:
            logger.error(f"Error deleting comment: {e}")
            return {"error": str(e)}

    # Resource Methods
    def get_projects_resource(self) -> List[Dict[str, Any]]:
        """Resource providing all Todoist projects"""
        return self.get_projects()

    def get_labels_resource(self) -> List[Dict[str, Any]]:
        """Resource providing all Todoist labels"""
        return self.get_labels()

    def get_today_tasks_resource(self) -> Dict[str, Any]:
        """Resource providing today's tasks using native Todoist filtering"""
        try:
            # Use native filter API for proper timezone handling
            tasks = self.get_tasks_with_filter("today")
            today = datetime.now(self.timezone).date()
            return {
                "date": today.isoformat(),
                "timezone": self.timezone_str,
                "tasks": tasks,
                "tasks_count": len(tasks),
            }
        except Exception as e:
            logger.error(f"Error getting today's tasks: {e}")
            return {"error": str(e), "tasks": [], "tasks_count": 0}

    def get_overdue_tasks_resource(self) -> Dict[str, Any]:
        """Resource providing overdue tasks using native Todoist filtering"""
        try:
            # Use native filter API for proper timezone handling
            tasks = self.get_tasks_with_filter("overdue")
            today = datetime.now(self.timezone).date()
            return {
                "date": today.isoformat(),
                "timezone": self.timezone_str,
                "tasks": tasks,
                "tasks_count": len(tasks),
            }
        except Exception as e:
            logger.error(f"Error getting overdue tasks: {e}")
            return {"error": str(e), "tasks": [], "tasks_count": 0}

    def get_project_tasks_resource(self, project_id: str) -> Dict[str, Any]:
        """Resource providing tasks for a specific project"""
        try:
            tasks = self.get_tasks(project_id=project_id)
            return {"project_id": project_id, "tasks": tasks, "tasks_count": len(tasks)}
        except Exception as e:
            logger.error(f"Error getting tasks for project {project_id}: {e}")
            return {"error": str(e), "project_id": project_id}

    def get_label_tasks_resource(self, label_name: str) -> Dict[str, Any]:
        """Resource providing tasks with a specific label"""
        try:
            tasks = self.get_tasks(label=label_name)
            return {"label": label_name, "tasks": tasks, "tasks_count": len(tasks)}
        except Exception as e:
            logger.error(f"Error getting tasks for label {label_name}: {e}")
            return {"error": str(e), "label": label_name}

    def get_priority_tasks_resource(self, priority: str) -> Dict[str, Any]:
        """Resource providing tasks with a specific priority"""
        try:
            priority_int = int(priority)
            if priority_int not in [1, 2, 3, 4]:
                return {"error": "Priority must be 1, 2, 3, or 4", "priority": priority}

            tasks = self.get_tasks()
            priority_tasks = [
                task for task in tasks if task.get("priority") == priority_int
            ]
            return {
                "priority": priority_int,
                "tasks": priority_tasks,
                "tasks_count": len(priority_tasks),
            }
        except Exception as e:
            logger.error(f"Error getting tasks for priority {priority}: {e}")
            return {"error": str(e), "priority": priority}

    def get_filtered_tasks_resource(self, filter_string: str) -> Dict[str, Any]:
        """Resource providing tasks matching a Todoist filter using native API"""
        try:
            # Use native filter API for proper timezone handling
            tasks = self.get_tasks_with_filter(filter_string)
            return {
                "filter": filter_string,
                "timezone": self.timezone_str,
                "tasks": tasks,
                "tasks_count": len(tasks),
            }
        except Exception as e:
            logger.error(f"Error getting tasks with filter '{filter_string}': {e}")
            return {"error": str(e), "filter": filter_string}

    def get_project_details_resource(self, project_id: str) -> Dict[str, Any]:
        """Resource providing project details with task count"""
        try:
            project = self.get_project(project_id)
            tasks = self.get_tasks(project_id=project_id)

            # Count completed and active tasks
            active_tasks = [t for t in tasks if not t.get("is_completed", False)]

            return {
                "project": project,
                "active_tasks_count": len(active_tasks),
                "total_tasks_count": len(tasks),
            }
        except Exception as e:
            logger.error(f"Error getting project details for {project_id}: {e}")
            return {"error": str(e), "project_id": project_id}

    def get_inbox_tasks_resource(self) -> Dict[str, Any]:
        """Resource providing inbox tasks (no project assigned)"""
        try:
            # Get inbox project (usually has is_inbox_project=True)
            projects = self.get_projects()
            inbox_project = next(
                (p for p in projects if p.get("is_inbox_project")), None
            )

            if inbox_project:
                tasks = self.get_tasks(project_id=inbox_project["id"])
            else:
                # Fallback: get tasks with no project_id
                all_tasks = self.get_tasks()
                tasks = [t for t in all_tasks if not t.get("project_id")]

            return {"inbox": True, "tasks": tasks, "tasks_count": len(tasks)}
        except Exception as e:
            logger.error(f"Error getting inbox tasks: {e}")
            return {"error": str(e), "inbox": True}

    def get_priorities_resource(self) -> Dict[str, Any]:
        """Resource providing Todoist priority levels"""
        return {
            "priorities": [
                {
                    "level": 4,
                    "name": "Urgent",
                    "color": "red",
                    "description": "Highest priority - urgent tasks",
                },
                {
                    "level": 3,
                    "name": "High",
                    "color": "orange",
                    "description": "High priority tasks",
                },
                {
                    "level": 2,
                    "name": "Medium",
                    "color": "blue",
                    "description": "Medium priority tasks",
                },
                {
                    "level": 1,
                    "name": "Low",
                    "color": "grey",
                    "description": "Low priority tasks (default)",
                },
            ],
            "default": 1,
            "note": "Use priority 4 for urgent, 3 for high, 2 for medium, 1 for low/normal",
        }

    def get_colors_resource(self) -> Dict[str, Any]:
        """Resource providing available Todoist colors"""
        return {
            "colors": [
                {"id": 30, "name": "berry_red", "hex": "#b8256f"},
                {"id": 31, "name": "red", "hex": "#db4035"},
                {"id": 32, "name": "orange", "hex": "#ff9933"},
                {"id": 33, "name": "yellow", "hex": "#fad000"},
                {"id": 34, "name": "olive_green", "hex": "#afb83b"},
                {"id": 35, "name": "lime_green", "hex": "#7ecc49"},
                {"id": 36, "name": "green", "hex": "#299438"},
                {"id": 37, "name": "mint_green", "hex": "#6accbc"},
                {"id": 38, "name": "teal", "hex": "#158fad"},
                {"id": 39, "name": "sky_blue", "hex": "#14aaf5"},
                {"id": 40, "name": "light_blue", "hex": "#96c3eb"},
                {"id": 41, "name": "blue", "hex": "#4073ff"},
                {"id": 42, "name": "grape", "hex": "#884dff"},
                {"id": 43, "name": "violet", "hex": "#af38eb"},
                {"id": 44, "name": "lavender", "hex": "#eb96eb"},
                {"id": 45, "name": "magenta", "hex": "#e05194"},
                {"id": 46, "name": "salmon", "hex": "#ff8d85"},
                {"id": 47, "name": "charcoal", "hex": "#808080"},
                {"id": 48, "name": "grey", "hex": "#b8b8b8"},
                {"id": 49, "name": "taupe", "hex": "#ccac93"},
            ],
            "usage": "Use color name (e.g., 'red') or ID (e.g., 31) when creating projects or labels",
        }

    def get_common_filters_resource(self) -> Dict[str, Any]:
        """Resource providing common Todoist filter strings"""
        return {
            "filters": [
                {
                    "filter": "today",
                    "description": "Tasks due today (in YOUR timezone)",
                },
                {
                    "filter": "tomorrow",
                    "description": "Tasks due tomorrow (in YOUR timezone)",
                },
                {
                    "filter": "next 7 days",
                    "description": "Tasks due in the next 7 days (rolling window)",
                },
                {"filter": "overdue", "description": "Overdue tasks"},
                {"filter": "no date", "description": "Tasks without a due date"},
                {"filter": "p1", "description": "Priority 1 (highest) tasks"},
                {"filter": "p2", "description": "Priority 2 tasks"},
                {"filter": "p3", "description": "Priority 3 tasks"},
                {"filter": "p4", "description": "Priority 4 (normal) tasks"},
                {"filter": "@work", "description": "Tasks with 'work' label"},
                {"filter": "##Work", "description": "Tasks in 'Work' project"},
                {
                    "filter": "today & p1",
                    "description": "High priority tasks due today",
                },
                {"filter": "overdue | today", "description": "Overdue or due today"},
                {
                    "filter": "created before: -7 days",
                    "description": "Tasks created more than 7 days ago",
                },
                {"filter": "assigned to: me", "description": "Tasks assigned to you"},
            ],
            "note": "Combine filters with & (AND), | (OR), and ! (NOT) operators. Time-based filters use YOUR configured timezone.",
        }

    def get_all_due_today_resource(self) -> Dict[str, Any]:
        """Get all tasks due today plus overdue tasks using native filtering"""
        try:
            # Use combined filter for today and overdue
            tasks = self.get_tasks_with_filter("today | overdue")
            today = datetime.now(self.timezone).date()

            # Separate into today and overdue
            due_today = []
            overdue = []

            for task in tasks:
                task_date = self._extract_task_date(task)
                if task_date:
                    if task_date == today:
                        due_today.append(task)
                    elif task_date < today:
                        overdue.append(task)

            return {
                "date": today.isoformat(),
                "timezone": self.timezone_str,
                "due_today": due_today,
                "due_today_count": len(due_today),
                "overdue": overdue,
                "overdue_count": len(overdue),
                "total_count": len(due_today) + len(overdue),
            }
        except Exception as e:
            logger.error(f"Error getting all due today: {e}")
            return {"error": str(e), "due_today": [], "overdue": []}

    def get_week_tasks_resource(self) -> Dict[str, Any]:
        """Get all tasks for the next 7 days using native filtering"""
        try:
            # Use native filter for next 7 days
            tasks = self.get_tasks_with_filter("next 7 days")
            today = datetime.now(self.timezone).date()
            start_date = today
            end_date = today + timedelta(days=6)

            # Sort tasks by date
            tasks.sort(key=lambda t: self._extract_task_date(t) or date.max)

            return {
                "week_start": start_date.isoformat(),
                "week_end": end_date.isoformat(),
                "week_type": "rolling_7_days",
                "timezone": self.timezone_str,
                "tasks": tasks,
                "tasks_count": len(tasks),
            }
        except Exception as e:
            logger.error(f"Error getting week tasks: {e}")
            return {"error": str(e), "tasks": [], "tasks_count": 0}

    def get_high_priority_tasks_resource(self) -> Dict[str, Any]:
        """Get all high priority tasks (P1 and P2)"""
        tasks = self.get_tasks()

        urgent_tasks = [t for t in tasks if t.get("priority") == 4]  # P1
        high_tasks = [t for t in tasks if t.get("priority") == 3]  # P2

        return {
            "urgent_tasks": urgent_tasks,
            "urgent_count": len(urgent_tasks),
            "high_tasks": high_tasks,
            "high_count": len(high_tasks),
            "total_high_priority": len(urgent_tasks) + len(high_tasks),
        }

    def get_no_date_tasks_resource(self) -> Dict[str, Any]:
        """Get all tasks without a due date"""
        tasks = self.get_tasks()
        no_date_tasks = [t for t in tasks if not t.get("due")]

        # Group by project for better organization
        by_project = {}
        for task in no_date_tasks:
            project_id = task.get("project_id", "No Project")
            if project_id not in by_project:
                by_project[project_id] = []
            by_project[project_id].append(task)

        return {
            "tasks": no_date_tasks,
            "tasks_count": len(no_date_tasks),
            "by_project": by_project,
            "project_count": len(by_project),
        }

    def get_tasks_with_deadlines_resource(self) -> Dict[str, Any]:
        """Get all tasks that have deadlines specified in descriptions"""
        tasks = self.get_tasks()
        today = datetime.now(self.timezone).date()
        tasks_with_deadlines = []

        for task in tasks:
            deadline = self._extract_deadline_from_description(
                task.get("description", "")
            )
            if deadline:
                try:
                    deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
                    days_until_deadline = (deadline_date - today).days

                    task_info = task.copy()
                    task_info["deadline"] = deadline
                    task_info["days_until_deadline"] = days_until_deadline

                    # Add warning flags
                    if days_until_deadline < 0:
                        task_info["deadline_status"] = "OVERDUE"
                    elif days_until_deadline == 0:
                        task_info["deadline_status"] = "DUE_TODAY"
                    elif days_until_deadline <= 3:
                        task_info["deadline_status"] = "APPROACHING"
                    else:
                        task_info["deadline_status"] = "OK"

                    tasks_with_deadlines.append(task_info)
                except ValueError:
                    # Invalid date format in deadline
                    logger.warning(
                        f"Invalid deadline format in task {task.get('id')}: {deadline}"
                    )

        # Sort by deadline date
        tasks_with_deadlines.sort(key=lambda t: t["deadline"])

        return {
            "tasks": tasks_with_deadlines,
            "total_count": len(tasks_with_deadlines),
            "overdue_count": sum(
                1 for t in tasks_with_deadlines if t["deadline_status"] == "OVERDUE"
            ),
            "approaching_count": sum(
                1
                for t in tasks_with_deadlines
                if t["deadline_status"] in ["DUE_TODAY", "APPROACHING"]
            ),
            "timezone": self.timezone_str,
        }

    def get_task_stats_resource(self) -> Dict[str, Any]:
        """Get statistics about tasks"""
        tasks = self.get_tasks()
        today = datetime.now(self.timezone).date()

        stats = {
            "total_active": len(tasks),
            "by_priority": {
                "urgent": len([t for t in tasks if t.get("priority") == 4]),
                "high": len([t for t in tasks if t.get("priority") == 3]),
                "medium": len([t for t in tasks if t.get("priority") == 2]),
                "low": len([t for t in tasks if t.get("priority") == 1]),
            },
            "by_due": {
                "overdue": 0,
                "today": 0,
                "tomorrow": 0,
                "this_week": 0,
                "no_date": len([t for t in tasks if not t.get("due")]),
            },
            "with_labels": len([t for t in tasks if t.get("labels")]),
            "without_labels": len([t for t in tasks if not t.get("labels")]),
        }

        # Count tasks by due date
        tomorrow = today + timedelta(days=1)
        week_end = today + timedelta(days=7)

        for task in tasks:
            if task.get("due"):
                due_date = task["due"].get("date")
                if due_date:
                    # due_date is already a date object from the API
                    if isinstance(due_date, date):
                        if due_date < today:
                            stats["by_due"]["overdue"] += 1
                        elif due_date == today:
                            stats["by_due"]["today"] += 1
                        elif due_date == tomorrow:
                            stats["by_due"]["tomorrow"] += 1
                        elif due_date <= week_end:
                            stats["by_due"]["this_week"] += 1
                    elif isinstance(due_date, str):
                        # Fallback if it's a string
                        try:
                            task_date = datetime.fromisoformat(
                                due_date.replace("Z", "+00:00")
                            ).date()
                            if task_date < today:
                                stats["by_due"]["overdue"] += 1
                            elif task_date == today:
                                stats["by_due"]["today"] += 1
                            elif task_date == tomorrow:
                                stats["by_due"]["tomorrow"] += 1
                            elif task_date <= week_end:
                                stats["by_due"]["this_week"] += 1
                        except Exception as exc:
                            logger.debug(
                                "Failed to bucket task by due date %r: %s",
                                due_date,
                                exc,
                            )

        return stats
