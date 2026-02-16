"""
title: GitLab Integration
author: DALEC
version: 2.0.0
description: Full GitLab API v4 integration — projects, repos, issues, MRs, CI/CD, members, wiki, snippets.
"""

import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
import base64
from enum import Enum
from typing import Callable, Any
from pydantic import BaseModel, Field


# -- Enums for finite sets --

class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class PipelineStatus(str, Enum):
    RUNNING = "running"
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"
    SKIPPED = "skipped"
    MANUAL = "manual"
    CREATED = "created"
    WAITING_FOR_RESOURCE = "waiting_for_resource"
    PREPARING = "preparing"
    SCHEDULED = "scheduled"


class IssueState(str, Enum):
    OPENED = "opened"
    CLOSED = "closed"
    ALL = "all"


class MrState(str, Enum):
    OPENED = "opened"
    CLOSED = "closed"
    MERGED = "merged"
    LOCKED = "locked"
    ALL = "all"


class AccessLevel(int, Enum):
    GUEST = 10
    REPORTER = 20
    DEVELOPER = 30
    MAINTAINER = 40
    OWNER = 50


class SearchScope(str, Enum):
    BLOBS = "blobs"
    COMMITS = "commits"
    ISSUES = "issues"
    MERGE_REQUESTS = "merge_requests"
    MILESTONES = "milestones"
    NOTES = "notes"
    WIKI_BLOBS = "wiki_blobs"


class OrderBy(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    LAST_ACTIVITY_AT = "last_activity_at"
    NAME = "name"
    PATH = "path"
    SIMILARITY = "similarity"


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class MergeMethod(str, Enum):
    MERGE = "merge"
    REBASE_MERGE = "rebase_merge"
    SQUASH = "squash"


# -- Protocol constants --

API_TIMEOUT_SECONDS = 30
MAX_PER_PAGE = 100
DEFAULT_PER_PAGE = 20
DEFAULT_PIPELINE_COUNT = 10
DEFAULT_TAIL_LINES = 100
AUTH_HEADER = "PRIVATE-TOKEN"
CONTENT_TYPE_JSON = "application/json"
LOG_DECODE_ERRORS = "replace"


# -- Open WebUI Tool Class --

class Tools:
    class Valves(BaseModel):
        gitlab_url: str = Field(
            default="https://code.levelup.cce.af.mil",
            description="GitLab instance URL"
        )
        gitlab_token: str = Field(
            default="",
            description="Personal Access Token (api + read_repository scopes)"
        )
        verify_ssl: bool = Field(
            default=True,
            description="Verify SSL certificates (set False for self-signed certs)"
        )

    def __init__(self):
        self.valves = self.Valves()

    async def _api(
        self,
        endpoint: str,
        *,
        method: HttpMethod = HttpMethod.GET,
        data: dict | None = None,
        project_path: str | None = None,
        description: str = "",
        raw: bool = False,
        __event_emitter__: Callable[[dict], Any] | None = None,
    ) -> dict | list | str:
        """
        Centralized API request handler.

        :param endpoint: API endpoint path (will be prefixed with /api/v4)
        :param method: HTTP method (GET, POST, PUT, DELETE)
        :param data: Request body data (will be JSON-encoded)
        :param project_path: If provided, URL-encode and interpolate /projects/{encoded} prefix
        :param description: Status message for event emitter
        :param raw: Return raw text response instead of JSON-parsed
        :param __event_emitter__: Event emitter callback
        :return: Parsed JSON response or raw text
        """
        try:
            # Emit start status
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": description, "done": False}
                })

            # Build URL
            if project_path:
                encoded_path = urllib.parse.quote(project_path, safe="")
                endpoint = f"/projects/{encoded_path}{endpoint}"

            url = f"{self.valves.gitlab_url.rstrip('/')}/api/v4{endpoint}"

            # Build request
            headers = {
                AUTH_HEADER: self.valves.gitlab_token,
            }

            if data is not None:
                headers[CONTENT_TYPE_JSON] = CONTENT_TYPE_JSON
                body = json.dumps(data).encode("utf-8")
            else:
                body = None

            req = urllib.request.Request(
                url,
                data=body,
                headers=headers,
                method=method.value
            )

            # SSL context
            if self.valves.verify_ssl:
                context = ssl.create_default_context()
            else:
                context = ssl._create_unverified_context()

            # Execute request
            with urllib.request.urlopen(req, context=context, timeout=API_TIMEOUT_SECONDS) as response:
                response_body = response.read().decode("utf-8", errors=LOG_DECODE_ERRORS)

                # Emit done status
                if __event_emitter__:
                    await __event_emitter__({
                        "type": "status",
                        "data": {"description": description, "done": True}
                    })

                if raw:
                    return response_body

                if response_body:
                    return json.loads(response_body)
                else:
                    # Empty response (e.g., 204 No Content)
                    return {"success": True}

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors=LOG_DECODE_ERRORS)
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": f"Error: {description}", "done": True}
                })
            return {
                "error": f"HTTP {e.code}: {e.reason}",
                "detail": error_body
            }
        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": f"Error: {description}", "done": True}
                })
            return {
                "error": str(type(e).__name__),
                "detail": str(e)
            }

    # -- Navigation & Discovery --

    async def list_projects(
        self,
        membership: bool = True,
        order_by: str = "last_activity_at",
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List GitLab projects.

        :param membership: Show only projects user is a member of
        :param order_by: Order by field (created_at, updated_at, last_activity_at, name, path)
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of projects
        """
        params = {k: v for k, v in {
            "membership": "true" if membership else None,
            "order_by": order_by,
            "per_page": str(min(per_page, MAX_PER_PAGE)),
        }.items() if v is not None}

        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())
        endpoint = f"/projects?{qs}" if qs else "/projects"

        result = await self._api(
            endpoint,
            description="Listing projects",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def get_project(
        self,
        project_path: str,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Get details of a specific project.

        :param project_path: Project path (namespace/project) or numeric ID
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with project details
        """
        encoded_path = urllib.parse.quote(project_path, safe="")
        result = await self._api(
            f"/projects/{encoded_path}",
            description=f"Getting project {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def list_groups(
        self,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List GitLab groups.

        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of groups
        """
        params = {"per_page": str(min(per_page, MAX_PER_PAGE))}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/groups?{qs}",
            description="Listing groups",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def list_group_projects(
        self,
        group_id: str,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List projects in a group.

        :param group_id: Group ID or path
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of projects
        """
        encoded_id = urllib.parse.quote(group_id, safe="")
        params = {"per_page": str(min(per_page, MAX_PER_PAGE))}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/groups/{encoded_id}/projects?{qs}",
            description=f"Listing projects in group {group_id}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    # -- Users & Identity --

    async def get_current_user(
        self,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Get current authenticated user details.

        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with user details
        """
        result = await self._api(
            "/user",
            description="Getting current user",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def search_users(
        self,
        search: str,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Search for users.

        :param search: Search query
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of users
        """
        params = {
            "search": search,
            "per_page": str(min(per_page, MAX_PER_PAGE))
        }
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/users?{qs}",
            description=f"Searching users: {search}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    # -- Project Members --

    async def list_project_members(
        self,
        project_path: str,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List members of a project.

        :param project_path: Project path (namespace/project)
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of members
        """
        params = {"per_page": str(min(per_page, MAX_PER_PAGE))}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/members?{qs}",
            project_path=project_path,
            description=f"Listing members of {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def add_project_member(
        self,
        project_path: str,
        user_id: int,
        access_level: int = AccessLevel.DEVELOPER.value,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Add a member to a project.

        :param project_path: Project path (namespace/project)
        :param user_id: User ID to add
        :param access_level: Access level (10=GUEST, 20=REPORTER, 30=DEVELOPER, 40=MAINTAINER, 50=OWNER)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with member details
        """
        data = {
            "user_id": user_id,
            "access_level": access_level
        }

        result = await self._api(
            "/members",
            method=HttpMethod.POST,
            data=data,
            project_path=project_path,
            description=f"Adding member {user_id} to {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def update_project_member(
        self,
        project_path: str,
        user_id: int,
        access_level: int,
        expires_at: str = None,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Update a project member's access level.

        :param project_path: Project path (namespace/project)
        :param user_id: User ID to update
        :param access_level: New access level (10=GUEST, 20=REPORTER, 30=DEVELOPER, 40=MAINTAINER, 50=OWNER)
        :param expires_at: Optional expiration date (ISO 8601 format)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with updated member details
        """
        data = {k: v for k, v in {
            "access_level": access_level,
            "expires_at": expires_at
        }.items() if v is not None}

        result = await self._api(
            f"/members/{user_id}",
            method=HttpMethod.PUT,
            data=data,
            project_path=project_path,
            description=f"Updating member {user_id} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def remove_project_member(
        self,
        project_path: str,
        user_id: int,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Remove a member from a project.

        :param project_path: Project path (namespace/project)
        :param user_id: User ID to remove
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON success response
        """
        result = await self._api(
            f"/members/{user_id}",
            method=HttpMethod.DELETE,
            project_path=project_path,
            description=f"Removing member {user_id} from {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    # -- Group Members --

    async def list_group_members(
        self,
        group_id: str,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List members of a group.

        :param group_id: Group ID or path
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of members
        """
        encoded_id = urllib.parse.quote(group_id, safe="")
        params = {"per_page": str(min(per_page, MAX_PER_PAGE))}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/groups/{encoded_id}/members?{qs}",
            description=f"Listing members of group {group_id}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def add_group_member(
        self,
        group_id: str,
        user_id: int,
        access_level: int = AccessLevel.DEVELOPER.value,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Add a member to a group.

        :param group_id: Group ID or path
        :param user_id: User ID to add
        :param access_level: Access level (10=GUEST, 20=REPORTER, 30=DEVELOPER, 40=MAINTAINER, 50=OWNER)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with member details
        """
        encoded_id = urllib.parse.quote(group_id, safe="")
        data = {
            "user_id": user_id,
            "access_level": access_level
        }

        result = await self._api(
            f"/groups/{encoded_id}/members",
            method=HttpMethod.POST,
            data=data,
            description=f"Adding member {user_id} to group {group_id}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def update_group_member(
        self,
        group_id: str,
        user_id: int,
        access_level: int,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Update a group member's access level.

        :param group_id: Group ID or path
        :param user_id: User ID to update
        :param access_level: New access level (10=GUEST, 20=REPORTER, 30=DEVELOPER, 40=MAINTAINER, 50=OWNER)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with updated member details
        """
        encoded_id = urllib.parse.quote(group_id, safe="")
        data = {"access_level": access_level}

        result = await self._api(
            f"/groups/{encoded_id}/members/{user_id}",
            method=HttpMethod.PUT,
            data=data,
            description=f"Updating member {user_id} in group {group_id}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def remove_group_member(
        self,
        group_id: str,
        user_id: int,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Remove a member from a group.

        :param group_id: Group ID or path
        :param user_id: User ID to remove
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON success response
        """
        encoded_id = urllib.parse.quote(group_id, safe="")

        result = await self._api(
            f"/groups/{encoded_id}/members/{user_id}",
            method=HttpMethod.DELETE,
            description=f"Removing member {user_id} from group {group_id}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    # -- Repository & Files --

    async def list_repository_tree(
        self,
        project_path: str,
        path: str = "",
        ref: str = "main",
        recursive: bool = False,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List repository tree (files and directories).

        :param project_path: Project path (namespace/project)
        :param path: Path inside repository
        :param ref: Branch/tag/commit ref
        :param recursive: Recursively list subdirectories
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of tree entries
        """
        params = {k: v for k, v in {
            "path": path or None,
            "ref": ref,
            "recursive": "true" if recursive else None,
            "per_page": str(MAX_PER_PAGE)
        }.items() if v is not None}

        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/repository/tree?{qs}",
            project_path=project_path,
            description=f"Listing repository tree for {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def get_file_contents(
        self,
        project_path: str,
        file_path: str,
        ref: str = "main",
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Get file contents from repository.

        :param project_path: Project path (namespace/project)
        :param file_path: Path to file in repository
        :param ref: Branch/tag/commit ref
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with file metadata and base64-decoded content
        """
        encoded_file_path = urllib.parse.quote(file_path, safe="")
        params = {"ref": ref}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/repository/files/{encoded_file_path}?{qs}",
            project_path=project_path,
            description=f"Getting file {file_path} from {project_path}",
            __event_emitter__=__event_emitter__
        )

        # Decode base64 content if present
        if isinstance(result, dict) and "content" in result:
            try:
                result["content_decoded"] = base64.b64decode(result["content"]).decode("utf-8", errors=LOG_DECODE_ERRORS)
            except Exception:
                result["content_decoded"] = None

        return json.dumps(result, indent=2)

    async def create_or_update_file(
        self,
        project_path: str,
        file_path: str,
        branch: str,
        content: str,
        commit_message: str,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Create or update a file in repository.

        :param project_path: Project path (namespace/project)
        :param file_path: Path to file in repository
        :param branch: Branch name
        :param content: File content (will be base64-encoded)
        :param commit_message: Commit message
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with file details
        """
        encoded_file_path = urllib.parse.quote(file_path, safe="")
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        data = {
            "branch": branch,
            "content": encoded_content,
            "commit_message": commit_message,
            "encoding": "base64"
        }

        result = await self._api(
            f"/repository/files/{encoded_file_path}",
            method=HttpMethod.PUT,
            data=data,
            project_path=project_path,
            description=f"Updating file {file_path} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def search_code(
        self,
        project_path: str,
        search: str,
        ref: str = "main",
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Search code in project repository.

        :param project_path: Project path (namespace/project)
        :param search: Search query
        :param ref: Branch/tag/commit ref
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of search results
        """
        params = {
            "scope": SearchScope.BLOBS.value,
            "search": search,
            "ref": ref
        }
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/search?{qs}",
            project_path=project_path,
            description=f"Searching code in {project_path}: {search}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    # -- Commits & Diffs --

    async def list_commits(
        self,
        project_path: str,
        ref_name: str = "main",
        path: str = None,
        since: str = None,
        until: str = None,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List repository commits.

        :param project_path: Project path (namespace/project)
        :param ref_name: Branch/tag/commit ref
        :param path: Path filter
        :param since: Start date (ISO 8601)
        :param until: End date (ISO 8601)
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of commits
        """
        params = {k: v for k, v in {
            "ref_name": ref_name,
            "path": path,
            "since": since,
            "until": until,
            "per_page": str(min(per_page, MAX_PER_PAGE))
        }.items() if v is not None}

        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/repository/commits?{qs}",
            project_path=project_path,
            description=f"Listing commits for {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def get_commit(
        self,
        project_path: str,
        sha: str,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Get details of a specific commit.

        :param project_path: Project path (namespace/project)
        :param sha: Commit SHA
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with commit details
        """
        result = await self._api(
            f"/repository/commits/{sha}",
            project_path=project_path,
            description=f"Getting commit {sha} from {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def compare(
        self,
        project_path: str,
        from_ref: str,
        to_ref: str,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Compare two branches, tags, or commits.

        :param project_path: Project path (namespace/project)
        :param from_ref: Source branch/tag/commit
        :param to_ref: Target branch/tag/commit
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with comparison details
        """
        params = {
            "from": from_ref,
            "to": to_ref
        }
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/repository/compare?{qs}",
            project_path=project_path,
            description=f"Comparing {from_ref} to {to_ref} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    # -- Branches & Tags --

    async def list_branches(
        self,
        project_path: str,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List repository branches.

        :param project_path: Project path (namespace/project)
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of branches
        """
        params = {"per_page": str(min(per_page, MAX_PER_PAGE))}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/repository/branches?{qs}",
            project_path=project_path,
            description=f"Listing branches for {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def create_branch(
        self,
        project_path: str,
        branch: str,
        ref: str,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Create a new branch.

        :param project_path: Project path (namespace/project)
        :param branch: New branch name
        :param ref: Source branch/tag/commit
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with branch details
        """
        data = {
            "branch": branch,
            "ref": ref
        }

        result = await self._api(
            "/repository/branches",
            method=HttpMethod.POST,
            data=data,
            project_path=project_path,
            description=f"Creating branch {branch} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def list_tags(
        self,
        project_path: str,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List repository tags.

        :param project_path: Project path (namespace/project)
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of tags
        """
        params = {"per_page": str(min(per_page, MAX_PER_PAGE))}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/repository/tags?{qs}",
            project_path=project_path,
            description=f"Listing tags for {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    # -- Issues --

    async def list_project_issues(
        self,
        project_path: str,
        state: str = IssueState.OPENED.value,
        labels: str = None,
        search: str = None,
        assignee_username: str = None,
        milestone: str = None,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List project issues.

        :param project_path: Project path (namespace/project)
        :param state: Issue state (opened, closed, all)
        :param labels: Comma-separated label names
        :param search: Search query
        :param assignee_username: Filter by assignee username
        :param milestone: Filter by milestone title
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of issues
        """
        params = {k: v for k, v in {
            "state": state,
            "labels": labels,
            "search": search,
            "assignee_username": assignee_username,
            "milestone": milestone,
            "per_page": str(min(per_page, MAX_PER_PAGE))
        }.items() if v is not None}

        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/issues?{qs}",
            project_path=project_path,
            description=f"Listing issues for {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def create_issue(
        self,
        project_path: str,
        title: str,
        description: str = None,
        assignee_usernames: str = None,
        labels: str = None,
        milestone_id: int = None,
        due_date: str = None,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Create a new issue.

        :param project_path: Project path (namespace/project)
        :param title: Issue title
        :param description: Issue description
        :param assignee_usernames: Comma-separated usernames
        :param labels: Comma-separated label names
        :param milestone_id: Milestone ID
        :param due_date: Due date (ISO 8601)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with created issue
        """
        data = {k: v for k, v in {
            "title": title,
            "description": description,
            "assignee_usernames": assignee_usernames,
            "labels": labels,
            "milestone_id": milestone_id,
            "due_date": due_date
        }.items() if v is not None}

        result = await self._api(
            "/issues",
            method=HttpMethod.POST,
            data=data,
            project_path=project_path,
            description=f"Creating issue in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def update_issue(
        self,
        project_path: str,
        issue_iid: int,
        state_event: str = None,
        labels: str = None,
        assignee_usernames: str = None,
        milestone_id: int = None,
        due_date: str = None,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Update an existing issue.

        :param project_path: Project path (namespace/project)
        :param issue_iid: Issue IID (internal ID)
        :param state_event: State event (close or reopen)
        :param labels: Comma-separated label names
        :param assignee_usernames: Comma-separated usernames
        :param milestone_id: Milestone ID
        :param due_date: Due date (ISO 8601)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with updated issue
        """
        data = {k: v for k, v in {
            "state_event": state_event,
            "labels": labels,
            "assignee_usernames": assignee_usernames,
            "milestone_id": milestone_id,
            "due_date": due_date
        }.items() if v is not None}

        result = await self._api(
            f"/issues/{issue_iid}",
            method=HttpMethod.PUT,
            data=data,
            project_path=project_path,
            description=f"Updating issue {issue_iid} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def list_issue_notes(
        self,
        project_path: str,
        issue_iid: int,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List notes (comments) on an issue.

        :param project_path: Project path (namespace/project)
        :param issue_iid: Issue IID (internal ID)
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of notes
        """
        params = {"per_page": str(min(per_page, MAX_PER_PAGE))}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/issues/{issue_iid}/notes?{qs}",
            project_path=project_path,
            description=f"Listing notes for issue {issue_iid} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def create_issue_note(
        self,
        project_path: str,
        issue_iid: int,
        body: str,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Create a note (comment) on an issue.

        :param project_path: Project path (namespace/project)
        :param issue_iid: Issue IID (internal ID)
        :param body: Note body
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with created note
        """
        data = {"body": body}

        result = await self._api(
            f"/issues/{issue_iid}/notes",
            method=HttpMethod.POST,
            data=data,
            project_path=project_path,
            description=f"Creating note on issue {issue_iid} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    # -- Merge Requests --

    async def list_merge_requests(
        self,
        project_path: str,
        state: str = MrState.OPENED.value,
        scope: str = "all",
        labels: str = None,
        search: str = None,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List merge requests.

        :param project_path: Project path (namespace/project)
        :param state: MR state (opened, closed, merged, locked, all)
        :param scope: Scope (created_by_me, assigned_to_me, all)
        :param labels: Comma-separated label names
        :param search: Search query
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of merge requests
        """
        params = {k: v for k, v in {
            "state": state,
            "scope": scope,
            "labels": labels,
            "search": search,
            "per_page": str(min(per_page, MAX_PER_PAGE))
        }.items() if v is not None}

        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/merge_requests?{qs}",
            project_path=project_path,
            description=f"Listing merge requests for {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def get_merge_request_details(
        self,
        project_path: str,
        mr_iid: int,
        include_changes: bool = False,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Get details of a merge request.

        :param project_path: Project path (namespace/project)
        :param mr_iid: Merge request IID (internal ID)
        :param include_changes: Include file changes
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with MR details
        """
        result = await self._api(
            f"/merge_requests/{mr_iid}",
            project_path=project_path,
            description=f"Getting merge request {mr_iid} from {project_path}",
            __event_emitter__=__event_emitter__
        )

        # Optionally fetch changes
        if include_changes and isinstance(result, dict) and "error" not in result:
            changes = await self._api(
                f"/merge_requests/{mr_iid}/changes",
                project_path=project_path,
                description=f"Getting changes for MR {mr_iid}",
                __event_emitter__=__event_emitter__
            )
            if isinstance(changes, dict) and "changes" in changes:
                result["changes"] = changes["changes"]

        return json.dumps(result, indent=2)

    async def create_merge_request(
        self,
        project_path: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str = None,
        assignee_usernames: str = None,
        labels: str = None,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Create a new merge request.

        :param project_path: Project path (namespace/project)
        :param source_branch: Source branch name
        :param target_branch: Target branch name
        :param title: MR title
        :param description: MR description
        :param assignee_usernames: Comma-separated usernames
        :param labels: Comma-separated label names
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with created MR
        """
        data = {k: v for k, v in {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
            "assignee_usernames": assignee_usernames,
            "labels": labels
        }.items() if v is not None}

        result = await self._api(
            "/merge_requests",
            method=HttpMethod.POST,
            data=data,
            project_path=project_path,
            description=f"Creating merge request in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def update_merge_request(
        self,
        project_path: str,
        mr_iid: int,
        state_event: str = None,
        assignee_usernames: str = None,
        labels: str = None,
        milestone_id: int = None,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Update a merge request.

        :param project_path: Project path (namespace/project)
        :param mr_iid: Merge request IID (internal ID)
        :param state_event: State event (close or reopen)
        :param assignee_usernames: Comma-separated usernames
        :param labels: Comma-separated label names
        :param milestone_id: Milestone ID
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with updated MR
        """
        data = {k: v for k, v in {
            "state_event": state_event,
            "assignee_usernames": assignee_usernames,
            "labels": labels,
            "milestone_id": milestone_id
        }.items() if v is not None}

        result = await self._api(
            f"/merge_requests/{mr_iid}",
            method=HttpMethod.PUT,
            data=data,
            project_path=project_path,
            description=f"Updating merge request {mr_iid} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def merge_merge_request(
        self,
        project_path: str,
        mr_iid: int,
        squash: bool = False,
        should_remove_source_branch: bool = False,
        merge_when_pipeline_succeeds: bool = False,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Merge a merge request.

        :param project_path: Project path (namespace/project)
        :param mr_iid: Merge request IID (internal ID)
        :param squash: Squash commits
        :param should_remove_source_branch: Remove source branch after merge
        :param merge_when_pipeline_succeeds: Auto-merge when pipeline succeeds
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with merge result
        """
        data = {
            "squash": squash,
            "should_remove_source_branch": should_remove_source_branch,
            "merge_when_pipeline_succeeds": merge_when_pipeline_succeeds
        }

        result = await self._api(
            f"/merge_requests/{mr_iid}/merge",
            method=HttpMethod.PUT,
            data=data,
            project_path=project_path,
            description=f"Merging merge request {mr_iid} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def list_mr_notes(
        self,
        project_path: str,
        mr_iid: int,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List notes (comments) on a merge request.

        :param project_path: Project path (namespace/project)
        :param mr_iid: Merge request IID (internal ID)
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of notes
        """
        params = {"per_page": str(min(per_page, MAX_PER_PAGE))}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/merge_requests/{mr_iid}/notes?{qs}",
            project_path=project_path,
            description=f"Listing notes for MR {mr_iid} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def create_mr_note(
        self,
        project_path: str,
        mr_iid: int,
        body: str,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Create a note (comment) on a merge request.

        :param project_path: Project path (namespace/project)
        :param mr_iid: Merge request IID (internal ID)
        :param body: Note body
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with created note
        """
        data = {"body": body}

        result = await self._api(
            f"/merge_requests/{mr_iid}/notes",
            method=HttpMethod.POST,
            data=data,
            project_path=project_path,
            description=f"Creating note on MR {mr_iid} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def mr_approvals(
        self,
        project_path: str,
        mr_iid: int,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Get approval status of a merge request.

        :param project_path: Project path (namespace/project)
        :param mr_iid: Merge request IID (internal ID)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with approval details
        """
        result = await self._api(
            f"/merge_requests/{mr_iid}/approvals",
            project_path=project_path,
            description=f"Getting approvals for MR {mr_iid} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    # -- Labels & Milestones --

    async def list_labels(
        self,
        project_path: str,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List project labels.

        :param project_path: Project path (namespace/project)
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of labels
        """
        params = {"per_page": str(min(per_page, MAX_PER_PAGE))}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/labels?{qs}",
            project_path=project_path,
            description=f"Listing labels for {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def list_milestones(
        self,
        project_path: str,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List project milestones.

        :param project_path: Project path (namespace/project)
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of milestones
        """
        params = {"per_page": str(min(per_page, MAX_PER_PAGE))}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/milestones?{qs}",
            project_path=project_path,
            description=f"Listing milestones for {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    # -- CI/CD Pipelines --

    async def get_project_pipelines(
        self,
        project_path: str,
        status: str = None,
        ref: str = None,
        count: int = DEFAULT_PIPELINE_COUNT,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Get project pipelines.

        :param project_path: Project path (namespace/project)
        :param status: Pipeline status (running, pending, success, failed, canceled, skipped, manual, created, waiting_for_resource, preparing, scheduled)
        :param ref: Branch/tag name
        :param count: Number of pipelines to return (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of pipelines
        """
        params = {k: v for k, v in {
            "status": status,
            "ref": ref,
            "per_page": str(min(count, MAX_PER_PAGE))
        }.items() if v is not None}

        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/pipelines?{qs}",
            project_path=project_path,
            description=f"Getting pipelines for {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def get_pipeline_jobs(
        self,
        project_path: str,
        pipeline_id: int,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Get jobs for a pipeline.

        :param project_path: Project path (namespace/project)
        :param pipeline_id: Pipeline ID
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of jobs
        """
        result = await self._api(
            f"/pipelines/{pipeline_id}/jobs",
            project_path=project_path,
            description=f"Getting jobs for pipeline {pipeline_id} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def get_job_log(
        self,
        project_path: str,
        job_id: int,
        tail_lines: int = DEFAULT_TAIL_LINES,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Get job log (tail last N lines).

        :param project_path: Project path (namespace/project)
        :param job_id: Job ID
        :param tail_lines: Number of lines from end to return
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: Last N lines of job log as text
        """
        result = await self._api(
            f"/jobs/{job_id}/trace",
            project_path=project_path,
            description=f"Getting log for job {job_id} in {project_path}",
            raw=True,
            __event_emitter__=__event_emitter__
        )

        if isinstance(result, str):
            lines = result.splitlines()
            tail = lines[-tail_lines:] if len(lines) > tail_lines else lines
            return "\n".join(tail)
        else:
            return json.dumps(result, indent=2)

    async def create_pipeline(
        self,
        project_path: str,
        ref: str,
        variables: dict = None,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Create a new pipeline.

        :param project_path: Project path (namespace/project)
        :param ref: Branch/tag name
        :param variables: Pipeline variables dict
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with created pipeline
        """
        data = {"ref": ref}
        if variables:
            data["variables"] = [
                {"key": k, "value": v} for k, v in variables.items()
            ]

        result = await self._api(
            "/pipeline",
            method=HttpMethod.POST,
            data=data,
            project_path=project_path,
            description=f"Creating pipeline for {ref} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def retry_job(
        self,
        project_path: str,
        job_id: int,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Retry a job.

        :param project_path: Project path (namespace/project)
        :param job_id: Job ID
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with job details
        """
        result = await self._api(
            f"/jobs/{job_id}/retry",
            method=HttpMethod.POST,
            project_path=project_path,
            description=f"Retrying job {job_id} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def cancel_job(
        self,
        project_path: str,
        job_id: int,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Cancel a job.

        :param project_path: Project path (namespace/project)
        :param job_id: Job ID
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with job details
        """
        result = await self._api(
            f"/jobs/{job_id}/cancel",
            method=HttpMethod.POST,
            project_path=project_path,
            description=f"Canceling job {job_id} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def list_pipeline_variables(
        self,
        project_path: str,
        pipeline_id: int,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List variables for a pipeline.

        :param project_path: Project path (namespace/project)
        :param pipeline_id: Pipeline ID
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of variables
        """
        result = await self._api(
            f"/pipelines/{pipeline_id}/variables",
            project_path=project_path,
            description=f"Listing variables for pipeline {pipeline_id} in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    # -- Snippets & Wiki --

    async def list_snippets(
        self,
        project_path: str,
        per_page: int = DEFAULT_PER_PAGE,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List project snippets.

        :param project_path: Project path (namespace/project)
        :param per_page: Results per page (max 100)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of snippets
        """
        params = {"per_page": str(min(per_page, MAX_PER_PAGE))}
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())

        result = await self._api(
            f"/snippets?{qs}",
            project_path=project_path,
            description=f"Listing snippets for {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def create_snippet(
        self,
        project_path: str,
        title: str,
        file_name: str,
        content: str,
        visibility: str = "private",
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Create a new snippet.

        :param project_path: Project path (namespace/project)
        :param title: Snippet title
        :param file_name: File name
        :param content: Snippet content
        :param visibility: Visibility (private, internal, public)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with created snippet
        """
        data = {
            "title": title,
            "file_name": file_name,
            "content": content,
            "visibility": visibility
        }

        result = await self._api(
            "/snippets",
            method=HttpMethod.POST,
            data=data,
            project_path=project_path,
            description=f"Creating snippet in {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def list_wiki_pages(
        self,
        project_path: str,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        List wiki pages.

        :param project_path: Project path (namespace/project)
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON array of wiki pages
        """
        result = await self._api(
            "/wikis",
            project_path=project_path,
            description=f"Listing wiki pages for {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)

    async def get_wiki_page(
        self,
        project_path: str,
        slug: str,
        __user__: dict = {},
        __event_emitter__: Callable[[dict], Any] = None
    ) -> str:
        """
        Get a wiki page by slug.

        :param project_path: Project path (namespace/project)
        :param slug: Wiki page slug
        :param __user__: User context
        :param __event_emitter__: Event emitter
        :return: JSON object with wiki page content
        """
        result = await self._api(
            f"/wikis/{slug}",
            project_path=project_path,
            description=f"Getting wiki page {slug} from {project_path}",
            __event_emitter__=__event_emitter__
        )
        return json.dumps(result, indent=2)
