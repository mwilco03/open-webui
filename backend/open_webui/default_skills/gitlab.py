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

log = logging.getLogger(__name__)

# Constants
MAX_DIFF_SIZE = 50000  # Default max diff size in bytes


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
    __request__=None,
    __user__=None,
) -> str:
    """Manage GitLab issues: search, get, create, update, comment."""
    try:
        from open_webui.env import GITLAB_URL, GITLAB_TOKEN, GITLAB_VERIFY_SSL
        import aiohttp
        from urllib.parse import quote

        if not GITLAB_TOKEN:
            return json.dumps({"error": "GitLab token not configured. Set GITLAB_TOKEN environment variable."})

        headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
        encoded_project_id = quote(project_id, safe="")

        async with aiohttp.ClientSession() as session:
            if action == "search":
                params = {"state": state}
                if search:
                    params["search"] = search
                if labels:
                    params["labels"] = labels

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/issues"
                async with session.get(url, headers=headers, params=params, ssl=GITLAB_VERIFY_SSL,
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

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/issues/{issue_id}"
                async with session.get(url, headers=headers, ssl=GITLAB_VERIFY_SSL,
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

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/issues"
                async with session.post(url, headers=headers, json=data, ssl=GITLAB_VERIFY_SSL,
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

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/issues/{issue_id}"
                async with session.put(url, headers=headers, json=data, ssl=GITLAB_VERIFY_SSL,
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

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/issues/{issue_id}/notes"
                data = {"body": comment_body}
                async with session.post(url, headers=headers, json=data, ssl=GITLAB_VERIFY_SSL,
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
    # BATCHING: Get multiple data in one call
    include_changes: bool = False,  # Include diff when action=get
    include_pipeline: bool = False,  # Include pipeline status when action=get
    # STREAMING: User-controlled limits
    max_diff_size: Optional[int] = None,  # None = full diff (user request), else limit
    __request__=None,
    __user__=None,
) -> str:
    """
    Manage GitLab merge requests with batching and streaming support.

    Batching: Set include_changes=True or include_pipeline=True with action=get
    Streaming: Large diffs auto-truncate unless user explicitly requests full content
    """
    try:
        from open_webui.env import GITLAB_URL, GITLAB_TOKEN, GITLAB_VERIFY_SSL
        import aiohttp
        from urllib.parse import quote

        if not GITLAB_TOKEN:
            return json.dumps({"error": "GitLab token not configured."})

        headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
        encoded_project_id = quote(project_id, safe="")

        async with aiohttp.ClientSession() as session:
            if action == "search":
                params = {"state": state}
                if search:
                    params["search"] = search
                if labels:
                    params["labels"] = labels

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests"
                async with session.get(url, headers=headers, params=params, ssl=GITLAB_VERIFY_SSL,
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

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests/{mr_id}"
                async with session.get(url, headers=headers, ssl=GITLAB_VERIFY_SSL,
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

                        # BATCHING: Include changes if requested
                        if include_changes:
                            changes_url = f"{url}/changes"
                            async with session.get(changes_url, headers=headers, ssl=GITLAB_VERIFY_SSL,
                                                 timeout=aiohttp.ClientTimeout(total=30)) as changes_resp:
                                if changes_resp.status == 200:
                                    changes_data = await changes_resp.json()
                                    changes = [{
                                        "old_path": c["old_path"], "new_path": c["new_path"],
                                        "diff": c["diff"], "new_file": c.get("new_file", False),
                                        "renamed_file": c.get("renamed_file", False),
                                        "deleted_file": c.get("deleted_file", False)
                                    } for c in changes_data.get("changes", [])]

                                    # STREAMING: Apply diff size limits
                                    total_diff_size = sum(len(c["diff"]) for c in changes)
                                    if max_diff_size is None and total_diff_size > MAX_DIFF_SIZE:
                                        # AI proactive fetch - apply limit
                                        result["changes"] = changes
                                        result["diff_truncated"] = True
                                        result["diff_message"] = f"Diff size {total_diff_size} bytes. Set max_diff_size=0 for full diff."
                                    else:
                                        result["changes"] = changes

                        # BATCHING: Include pipeline if requested
                        if include_pipeline:
                            pipeline_url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/pipelines"
                            async with session.get(pipeline_url, headers=headers,
                                                 params={"ref": mr["source_branch"], "per_page": 1},
                                                 ssl=GITLAB_VERIFY_SSL,
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

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests/{mr_id}/changes"
                async with session.get(url, headers=headers, ssl=GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        changes = [{
                            "old_path": c["old_path"], "new_path": c["new_path"], "diff": c["diff"],
                            "new_file": c.get("new_file", False), "renamed_file": c.get("renamed_file", False),
                            "deleted_file": c.get("deleted_file", False)
                        } for c in data.get("changes", [])]

                        # STREAMING: Handle large diffs
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

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests/{mr_id}/notes"
                async with session.post(url, headers=headers, json={"body": comment_body},
                                      ssl=GITLAB_VERIFY_SSL, timeout=aiohttp.ClientTimeout(total=30)) as response:
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

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests/{mr_id}/approve"
                async with session.post(url, headers=headers, ssl=GITLAB_VERIFY_SSL,
                                      timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 201:
                        return json.dumps({"status": "success", "message": "MR approved"})
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "merge":
                if not mr_id:
                    return json.dumps({"error": "mr_id required"})

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/merge_requests/{mr_id}/merge"
                data = {"should_remove_source_branch": should_remove_source_branch}
                if merge_commit_message:
                    data["merge_commit_message"] = merge_commit_message

                async with session.put(url, headers=headers, json=data, ssl=GITLAB_VERIFY_SSL,
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


async def gitlab_repository(
    project_id: str,
    action: str,  # get_file|commit_file|search_code|list_branches|get_commit|create_branch|delete_branch
    file_path: str = "",
    ref: str = "main",
    content: str = "",
    commit_message: str = "",
    branch: str = "",
    branch_name: str = "",
    search_query: str = "",
    commit_sha: str = "",
    # STREAMING: User-controlled limits
    max_file_size: Optional[int] = None,  # None = full file (user wants it all)
    __request__=None,
    __user__=None,
) -> str:
    """Manage GitLab repository: files, code search, branches, commits."""
    try:
        from open_webui.env import GITLAB_URL, GITLAB_TOKEN, GITLAB_VERIFY_SSL
        import aiohttp
        import base64
        from urllib.parse import quote

        if not GITLAB_TOKEN:
            return json.dumps({"error": "GitLab token not configured."})

        headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
        encoded_project_id = quote(project_id, safe="")

        async with aiohttp.ClientSession() as session:
            if action == "get_file":
                if not file_path:
                    return json.dumps({"error": "file_path required"})

                encoded_file_path = quote(file_path, safe="")
                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/repository/files/{encoded_file_path}"

                async with session.get(url, headers=headers, params={"ref": ref},
                                     ssl=GITLAB_VERIFY_SSL, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        file_content = base64.b64decode(data["content"]).decode("utf-8")
                        file_size = len(file_content)

                        # STREAMING: Apply size limits unless user wants full content
                        if max_file_size is None:
                            # User explicitly wants full file - return everything
                            return json.dumps({
                                "file_path": data["file_path"], "ref": ref,
                                "content": file_content, "size": file_size
                            }, ensure_ascii=False)
                        elif file_size > max_file_size:
                            # Truncate for AI proactive fetch
                            return json.dumps({
                                "file_path": data["file_path"], "ref": ref,
                                "content": file_content[:max_file_size],
                                "size": file_size, "truncated": True,
                                "message": f"Showing first {max_file_size} of {file_size} bytes. Set max_file_size=None for full file."
                            }, ensure_ascii=False)
                        else:
                            return json.dumps({
                                "file_path": data["file_path"], "ref": ref,
                                "content": file_content, "size": file_size
                            }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "commit_file":
                if not file_path or not content or not commit_message or not branch:
                    return json.dumps({"error": "file_path, content, commit_message, branch required"})

                encoded_file_path = quote(file_path, safe="")
                check_url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/repository/files/{encoded_file_path}"

                # Check if file exists
                async with session.get(check_url, headers=headers, params={"ref": branch},
                                     ssl=GITLAB_VERIFY_SSL, timeout=aiohttp.ClientTimeout(total=10)) as check_resp:
                    file_exists = check_resp.status == 200

                data = {"branch": branch, "content": content, "commit_message": commit_message}

                if file_exists:
                    async with session.put(check_url, headers=headers, json=data,
                                         ssl=GITLAB_VERIFY_SSL, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            result = await response.json()
                            return json.dumps({
                                "status": "success", "action": "updated",
                                "file_path": result["file_path"], "branch": result["branch"]
                            }, ensure_ascii=False)
                        else:
                            return json.dumps({"error": f"GitLab API error ({response.status})"})
                else:
                    async with session.post(check_url, headers=headers, json=data,
                                          ssl=GITLAB_VERIFY_SSL, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 201:
                            result = await response.json()
                            return json.dumps({
                                "status": "success", "action": "created",
                                "file_path": result["file_path"], "branch": result["branch"]
                            }, ensure_ascii=False)
                        else:
                            return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "search_code":
                if not search_query:
                    return json.dumps({"error": "search_query required"})

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/search"
                params = {"scope": "blobs", "search": search_query, "ref": ref}

                async with session.get(url, headers=headers, params=params,
                                     ssl=GITLAB_VERIFY_SSL, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        results = await response.json()
                        return json.dumps({"results": [{
                            "filename": r.get("filename", ""), "path": r.get("path", ""),
                            "data": r.get("data", ""), "ref": ref
                        } for r in results[:20]]}, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "list_branches":
                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/repository/branches"
                params = {}
                if search_query:
                    params["search"] = search_query

                async with session.get(url, headers=headers, params=params,
                                     ssl=GITLAB_VERIFY_SSL, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        branches = await response.json()
                        return json.dumps({"branches": [{
                            "name": b["name"], "protected": b.get("protected", False),
                            "default": b.get("default", False),
                            "last_commit": {
                                "id": b["commit"]["id"], "message": b["commit"]["message"],
                                "committed_date": b["commit"]["committed_date"]
                            }
                        } for b in branches]}, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "get_commit":
                if not commit_sha:
                    return json.dumps({"error": "commit_sha required"})

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/repository/commits/{commit_sha}"

                async with session.get(url, headers=headers, ssl=GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        commit = await response.json()
                        return json.dumps({
                            "id": commit["id"], "short_id": commit["short_id"],
                            "title": commit["title"], "message": commit["message"],
                            "author_name": commit["author_name"], "authored_date": commit["authored_date"],
                            "committer_name": commit["committer_name"], "committed_date": commit["committed_date"],
                            "web_url": commit["web_url"], "stats": commit.get("stats", {})
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "create_branch":
                if not branch_name or not ref:
                    return json.dumps({"error": "branch_name and ref required"})

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/repository/branches"
                data = {"branch": branch_name, "ref": ref}

                async with session.post(url, headers=headers, json=data, ssl=GITLAB_VERIFY_SSL,
                                      timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 201:
                        branch = await response.json()
                        return json.dumps({
                            "status": "success", "branch_name": branch["name"],
                            "commit_id": branch["commit"]["id"]
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "delete_branch":
                if not branch_name:
                    return json.dumps({"error": "branch_name required"})

                encoded_branch = quote(branch_name, safe="")
                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/repository/branches/{encoded_branch}"

                async with session.delete(url, headers=headers, ssl=GITLAB_VERIFY_SSL,
                                        timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 204:
                        return json.dumps({"status": "success", "message": f"Branch '{branch_name}' deleted"})
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            else:
                return json.dumps({"error": f"Unknown action: {action}"})

    except Exception as e:
        log.exception(f"gitlab_repository error: {e}")
        return json.dumps({"error": str(e)})


async def gitlab_cicd(
    project_id: str,
    action: str,  # get_pipeline|trigger_pipeline|list_jobs|get_job_logs|list_releases|get_release
    ref: str = "main",
    pipeline_id: Optional[str] = None,
    job_id: Optional[str] = None,
    tag_name: str = "",
    variables: str = "",  # JSON string for trigger_pipeline
    __request__=None,
    __user__=None,
) -> str:
    """Manage GitLab CI/CD: pipelines, jobs, releases."""
    try:
        from open_webui.env import GITLAB_URL, GITLAB_TOKEN, GITLAB_VERIFY_SSL
        import aiohttp
        from urllib.parse import quote

        if not GITLAB_TOKEN:
            return json.dumps({"error": "GitLab token not configured."})

        headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
        encoded_project_id = quote(project_id, safe="")

        async with aiohttp.ClientSession() as session:
            if action == "get_pipeline":
                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/pipelines"
                params = {"ref": ref, "per_page": 1}

                async with session.get(url, headers=headers, params=params,
                                     ssl=GITLAB_VERIFY_SSL, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        pipelines = await response.json()
                        if not pipelines:
                            return json.dumps({"message": f"No pipelines found for ref '{ref}'"})

                        p = pipelines[0]
                        return json.dumps({
                            "id": p["id"], "status": p["status"], "ref": p["ref"],
                            "sha": p["sha"], "web_url": p["web_url"],
                            "created_at": p["created_at"], "updated_at": p["updated_at"]
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "trigger_pipeline":
                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/pipeline"
                data = {"ref": ref}

                if variables:
                    try:
                        vars_dict = json.loads(variables)
                        data["variables"] = [{"key": k, "value": v} for k, v in vars_dict.items()]
                    except json.JSONDecodeError:
                        return json.dumps({"error": "Invalid JSON format for variables"})

                async with session.post(url, headers=headers, json=data, ssl=GITLAB_VERIFY_SSL,
                                      timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 201:
                        pipeline = await response.json()
                        return json.dumps({
                            "status": "success", "pipeline_id": pipeline["id"],
                            "pipeline_status": pipeline["status"], "ref": pipeline["ref"],
                            "web_url": pipeline["web_url"]
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "list_jobs":
                if not pipeline_id:
                    return json.dumps({"error": "pipeline_id required"})

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/pipelines/{pipeline_id}/jobs"

                async with session.get(url, headers=headers, ssl=GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        jobs = await response.json()
                        return json.dumps({"jobs": [{
                            "id": j["id"], "name": j["name"], "stage": j["stage"],
                            "status": j["status"], "ref": j["ref"], "web_url": j["web_url"]
                        } for j in jobs]}, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "get_job_logs":
                if not job_id:
                    return json.dumps({"error": "job_id required"})

                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/jobs/{job_id}/trace"

                async with session.get(url, headers=headers, ssl=GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        logs = await response.text()
                        # STREAMING: Truncate very large logs
                        if len(logs) > 10000:
                            return json.dumps({
                                "job_id": job_id,
                                "logs": logs[:10000],
                                "truncated": True,
                                "message": "Logs truncated to 10000 characters"
                            }, ensure_ascii=False)
                        return json.dumps({"job_id": job_id, "logs": logs}, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "list_releases":
                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/releases"

                async with session.get(url, headers=headers, ssl=GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        releases = await response.json()
                        return json.dumps({"releases": [{
                            "tag_name": r["tag_name"], "name": r.get("name", ""),
                            "description": r.get("description", ""),
                            "created_at": r["created_at"], "released_at": r.get("released_at")
                        } for r in releases]}, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "get_release":
                if not tag_name:
                    return json.dumps({"error": "tag_name required"})

                encoded_tag = quote(tag_name, safe="")
                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}/releases/{encoded_tag}"

                async with session.get(url, headers=headers, ssl=GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        release = await response.json()
                        return json.dumps({
                            "tag_name": release["tag_name"], "name": release.get("name", ""),
                            "description": release.get("description", ""),
                            "created_at": release["created_at"],
                            "released_at": release.get("released_at"),
                            "assets": release.get("assets", {})
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            else:
                return json.dumps({"error": f"Unknown action: {action}"})

    except Exception as e:
        log.exception(f"gitlab_cicd error: {e}")
        return json.dumps({"error": str(e)})


async def gitlab_project(
    action: str,  # get_info|search_repos
    project_id: str = "",
    search_query: str = "",
    __request__=None,
    __user__=None,
) -> str:
    """Manage GitLab projects: get info, search repos."""
    try:
        from open_webui.env import GITLAB_URL, GITLAB_TOKEN, GITLAB_VERIFY_SSL
        import aiohttp
        from urllib.parse import quote

        if not GITLAB_TOKEN:
            return json.dumps({"error": "GitLab token not configured."})

        headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}

        async with aiohttp.ClientSession() as session:
            if action == "get_info":
                if not project_id:
                    return json.dumps({"error": "project_id required"})

                encoded_project_id = quote(project_id, safe="")
                url = f"{GITLAB_URL}/api/v4/projects/{encoded_project_id}"

                async with session.get(url, headers=headers, ssl=GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        project = await response.json()
                        return json.dumps({
                            "id": project["id"], "name": project["name"],
                            "path": project["path_with_namespace"],
                            "description": project.get("description", ""),
                            "web_url": project["web_url"],
                            "default_branch": project.get("default_branch", ""),
                            "star_count": project.get("star_count", 0),
                            "forks_count": project.get("forks_count", 0)
                        }, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            elif action == "search_repos":
                if not search_query:
                    return json.dumps({"error": "search_query required"})

                url = f"{GITLAB_URL}/api/v4/projects"
                params = {"search": search_query, "per_page": 20}

                async with session.get(url, headers=headers, params=params, ssl=GITLAB_VERIFY_SSL,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        projects = await response.json()
                        return json.dumps({"repositories": [{
                            "id": p["id"], "name": p["name"],
                            "path": p["path_with_namespace"],
                            "description": p.get("description", ""),
                            "web_url": p["web_url"],
                            "default_branch": p.get("default_branch", "")
                        } for p in projects]}, ensure_ascii=False)
                    else:
                        return json.dumps({"error": f"GitLab API error ({response.status})"})

            else:
                return json.dumps({"error": f"Unknown action: {action}"})

    except Exception as e:
        log.exception(f"gitlab_project error: {e}")
        return json.dumps({"error": str(e)})
