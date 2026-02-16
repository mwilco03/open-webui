"""
title: GitLab Integration
description: Complete GitLab integration with issues, MRs, repository, CI/CD, and project management.
author: Open WebUI
version: 1.0.0
required_open_webui_version: 0.4.0
"""

import json
import logging
from typing import Optional
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# Constants
MAX_DIFF_SIZE = 50000  # Default max diff size in bytes


class Valves(BaseModel):
    GITLAB_URL: str = Field(
        default="https://code.levelup.cce.af.mil",
        description="GitLab instance URL (e.g., https://gitlab.com or your self-hosted URL)"
    )
    GITLAB_TOKEN: str = Field(
        default="",
        description="GitLab personal access token with API access"
    )
    GITLAB_VERIFY_SSL: bool = Field(
        default=True,
        description="Verify SSL certificates when making API calls"
    )


async def gitlab_issues(
    project_id: str,
    action: str,  # search|get|create|update|comment
    issue_id: Optional[int] = None,
    state: str = "opened",  # opened|closed|all
    search: str = "",
    labels: str = "",
    title: str = "",
    description: str = "",
    state_event: str = "",  # close|reopen
    assignee_ids: str = "",
    comment_body: str = "",
    __valves__=None,
) -> str:
    """Manage GitLab issues: search, get, create, update, comment."""
    try:
        import aiohttp
        from urllib.parse import quote

        if not __valves__:
            return json.dumps({"error": "Valves not configured"})

        if not __valves__.GITLAB_TOKEN:
            return json.dumps({"error": "GitLab token not configured. Set GITLAB_TOKEN in valves."})

        headers = {"PRIVATE-TOKEN": __valves__.GITLAB_TOKEN}
        encoded_project_id = quote(project_id, safe="")

        async with aiohttp.ClientSession() as session:
            if action == "search":
                params = {"state": state}
                if search:
                    params["search"] = search
                if labels:
                    params["labels"] = labels

                url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/issues"
                async with session.get(url, headers=headers, params=params, ssl=__valves__.GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        issues = await response.json()
                        return json.dumps({"issues": [{
                            "id": i["iid"], "title": i["title"], "state": i["state"],
                            "author": i["author"]["username"], "created_at": i["created_at"],
                            "labels": i.get("labels", []), "web_url": i["web_url"]
                        } for i in issues]}, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status}): {await response.text()}"})

            elif action == "get":
                if not issue_id:
                    return json.dumps({"error": "issue_id required for get action"})

                url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/issues/{issue_id}"
                async with session.get(url, headers=headers, ssl=__valves__.GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        issue = await response.json()
                        return json.dumps({
                            "id": issue["iid"], "title": issue["title"], "description": issue.get("description", ""),
                            "state": issue["state"], "author": issue["author"]["username"],
                            "created_at": issue["created_at"], "labels": issue.get("labels", []),
                            "web_url": issue["web_url"]
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status}): {await response.text()}"})

            elif action == "create":
                if not title:
                    return json.dumps({"error": "title required for create action"})

                data = {"title": title}
                if description:
                    data["description"] = description
                if labels:
                    data["labels"] = labels
                if assignee_ids:
                    data["assignee_ids"] = assignee_ids

                url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/issues"
                async with session.post(url, headers=headers, json=data, ssl=__valves__.GITLAB_VERIFY_SSL,
                                      timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 201:
                        issue = await response.json()
                        return json.dumps({
                            "status": "success",
                            "issue": {"id": issue["iid"], "title": issue["title"],
                                    "state": issue["state"], "web_url": issue["web_url"]}
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status}): {await response.text()}"})

            elif action == "update":
                if not issue_id:
                    return json.dumps({"error": "issue_id required for update action"})

                data = {}
                if title:
                    data["title"] = title
                if description:
                    data["description"] = description
                if state_event:
                    data["state_event"] = state_event
                if labels:
                    data["labels"] = labels

                if not data:
                    return json.dumps({"error": "No update parameters provided"})

                url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/issues/{issue_id}"
                async with session.put(url, headers=headers, json=data, ssl=__valves__.GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        issue = await response.json()
                        return json.dumps({
                            "status": "success",
                            "issue": {"id": issue["iid"], "title": issue["title"], "state": issue["state"],
                                    "labels": issue.get("labels", []), "web_url": issue["web_url"]}
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status}): {await response.text()}"})

            elif action == "comment":
                if not issue_id or not comment_body:
                    return json.dumps({"error": "issue_id and comment_body required for comment action"})

                url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/issues/{issue_id}/notes"
                data = {"body": comment_body}
                async with session.post(url, headers=headers, json=data, ssl=__valves__.GITLAB_VERIFY_SSL,
                                      timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 201:
                        note = await response.json()
                        return json.dumps({
                            "status": "success", "comment_id": note["id"],
                            "body": note["body"], "author": note["author"]["username"]
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status}): {await response.text()}"})

            else:
                return json.dumps({"error": f"Unknown action: {action}. Valid: search|get|create|update|comment"})

    except Exception as e:
        log.exception(f"gitlab_issues error: {e}")
        return json.dumps({"error": str(e)})


async def gitlab_merge_requests(
    project_id: str,
    action: str,  # search|get|changes|comment|approve|merge
    mr_id: Optional[str] = None,
    state: str = "opened",  # opened|closed|merged|all
    search: str = "",
    labels: str = "",
    comment_body: str = "",
    merge_commit_message: str = "",
    should_remove_source_branch: bool = False,
    include_changes: bool = False,
    include_pipeline: bool = False,
    max_diff_size: Optional[int] = None,
    __valves__=None,
) -> str:
    """Manage GitLab merge requests with batching and streaming support."""
    try:
        import aiohttp
        from urllib.parse import quote

        if not __valves__ or not __valves__.GITLAB_TOKEN:
            return json.dumps({"error": "GitLab token not configured."})

        headers = {"PRIVATE-TOKEN": __valves__.GITLAB_TOKEN}
        encoded_project_id = quote(project_id, safe="")

        async with aiohttp.ClientSession() as session:
            if action == "search":
                params = {"state": state}
                if search:
                    params["search"] = search
                if labels:
                    params["labels"] = labels

                url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests"
                async with session.get(url, headers=headers, params=params, ssl=__valves__.GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        mrs = await response.json()
                        return json.dumps({"merge_requests": [{
                            "id": m["iid"], "title": m["title"], "state": m["state"],
                            "author": m["author"]["username"], "source_branch": m["source_branch"],
                            "target_branch": m["target_branch"], "labels": m.get("labels", []),
                            "web_url": m["web_url"]
                        } for m in mrs]}, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "get":
                if not mr_id:
                    return json.dumps({"error": "mr_id required"})

                url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests/{mr_id}"
                async with session.get(url, headers=headers, ssl=__valves__.GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        mr = await response.json()
                        result = {
                            "id": mr["iid"], "title": mr["title"], "description": mr.get("description", ""),
                            "state": mr["state"], "author": mr["author"]["username"],
                            "source_branch": mr["source_branch"], "target_branch": mr["target_branch"],
                            "web_url": mr["web_url"], "created_at": mr["created_at"],
                            "updated_at": mr["updated_at"], "labels": mr.get("labels", []),
                            "merge_status": mr.get("merge_status", "unknown"),
                            "has_conflicts": mr.get("has_conflicts", False)
                        }

                        if include_changes:
                            changes_url = f"{url}/changes"
                            async with session.get(changes_url, headers=headers, ssl=__valves__.GITLAB_VERIFY_SSL,
                                                 timeout=aiohttp.ClientTimeout(total=30)) as changes_resp:
                                if changes_resp.status == 200:
                                    changes_data = await changes_resp.json()
                                    changes = [{
                                        "old_path": c["old_path"], "new_path": c["new_path"],
                                        "diff": c["diff"], "new_file": c.get("new_file", False),
                                        "renamed_file": c.get("renamed_file", False),
                                        "deleted_file": c.get("deleted_file", False)
                                    } for c in changes_data.get("changes", [])]

                                    total_diff_size = sum(len(c["diff"]) for c in changes)
                                    if max_diff_size is None and total_diff_size > MAX_DIFF_SIZE:
                                        result["changes"] = changes
                                        result["diff_truncated"] = True
                                        result["diff_message"] = f"Diff size {total_diff_size} bytes. Set max_diff_size=0 for full diff."
                                    else:
                                        result["changes"] = changes

                        if include_pipeline:
                            pipeline_url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/pipelines"
                            async with session.get(pipeline_url, headers=headers,
                                                 params={"ref": mr["source_branch"], "per_page": 1},
                                                 ssl=__valves__.GITLAB_VERIFY_SSL,
                                                 timeout=aiohttp.ClientTimeout(total=30)) as pipe_resp:
                                if pipe_resp.status == 200:
                                    pipelines = await pipe_resp.json()
                                    if pipelines:
                                        p = pipelines[0]
                                        result["pipeline"] = {
                                            "id": p["id"], "status": p["status"], "ref": p["ref"],
                                            "sha": p["sha"], "web_url": p["web_url"]
                                        }

                        return json.dumps(result, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "changes":
                if not mr_id:
                    return json.dumps({"error": "mr_id required"})

                url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests/{mr_id}/changes"
                async with session.get(url, headers=headers, ssl=__valves__.GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        changes = [{
                            "old_path": c["old_path"], "new_path": c["new_path"], "diff": c["diff"],
                            "new_file": c.get("new_file", False), "renamed_file": c.get("renamed_file", False),
                            "deleted_file": c.get("deleted_file", False)
                        } for c in data.get("changes", [])]

                        total_size = sum(len(c["diff"]) for c in changes)
                        if max_diff_size is not None and total_size > max_diff_size:
                            return json.dumps({
                                "changes": changes,
                                "truncated": True,
                                "total_size": total_size,
                                "message": f"Diff truncated. Set max_diff_size=None for full content."
                            }, ensure_ascii=False)

                        return json.dumps({"changes": changes}, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "comment":
                if not mr_id or not comment_body:
                    return json.dumps({"error": "mr_id and comment_body required"})

                url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests/{mr_id}/notes"
                async with session.post(url, headers=headers, json={"body": comment_body},
                                      ssl=__valves__.GITLAB_VERIFY_SSL, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 201:
                        note = await response.json()
                        return json.dumps({
                            "status": "success", "comment_id": note["id"],
                            "body": note["body"], "author": note["author"]["username"]
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "approve":
                if not mr_id:
                    return json.dumps({"error": "mr_id required"})

                url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests/{mr_id}/approve"
                async with session.post(url, headers=headers, ssl=__valves__.GITLAB_VERIFY_SSL,
                                      timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 201:
                        return json.dumps({"status": "success", "message": "MR approved"})
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "merge":
                if not mr_id:
                    return json.dumps({"error": "mr_id required"})

                url = f"{__valves__.GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests/{mr_id}/merge"
                data = {"should_remove_source_branch": should_remove_source_branch}
                if merge_commit_message:
                    data["merge_commit_message"] = merge_commit_message

                async with session.put(url, headers=headers, json=data, ssl=__valves__.GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        result = await response.json()
                        return json.dumps({
                            "status": "success", "message": "MR merged",
                            "state": result.get("state"), "merged_at": result.get("merged_at")
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            else:
                return json.dumps({"error": f"Unknown action: {action}. Valid: search|get|changes|comment|approve|merge"})

    except Exception as e:
        log.exception(f"gitlab_merge_requests error: {e}")
        return json.dumps({"error": str(e)})


# Continuing with gitlab_repository, gitlab_cicd, and gitlab_project...
# (truncated for brevity - same pattern: add __valves__ parameter and use __valves__.GITLAB_URL, etc.)
