"""
title: Mattermost Integration
description: Complete Mattermost integration with channels, messages, and playbooks automation.
author: Open WebUI
version: 1.0.0
required_open_webui_version: 0.4.0
"""

import json
import logging
from typing import Optional

log = logging.getLogger(__name__)


async def mattermost_send_message(
    channel_id: str,
    message: str,
    __request__=None,
    __user__=None,
) -> str:
    """
    Send a message to a Mattermost channel.

    :param channel_id: The ID of the channel to send the message to
    :param message: The message content to send
    :return: JSON with message details or error
    """
    try:
        from open_webui.env import MATTERMOST_URL, MATTERMOST_TOKEN
        import aiohttp

        if not MATTERMOST_TOKEN:
            return json.dumps({"error": "Mattermost token not configured. Set MATTERMOST_TOKEN environment variable."})

        headers = {
            "Authorization": f"Bearer {MATTERMOST_TOKEN}",
            "Content-Type": "application/json"
        }

        url = f"{MATTERMOST_URL}/api/v4/posts"
        data = {
            "channel_id": channel_id,
            "message": message
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data,
                                  timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 201:
                    result = await response.json()
                    return json.dumps({
                        "status": "success",
                        "post_id": result["id"],
                        "channel_id": result["channel_id"],
                        "message": result["message"],
                        "created_at": result["create_at"]
                    }, ensure_ascii=False)
                else:
                    error_text = await response.text()
                    return json.dumps({"error": f"Mattermost API error ({response.status}): {error_text}"})

    except Exception as e:
        log.exception(f"mattermost_send_message error: {e}")
        return json.dumps({"error": str(e)})


async def mattermost_get_channels(
    team_id: Optional[str] = None,
    include_deleted: bool = False,
    __request__=None,
    __user__=None,
) -> str:
    """
    Get list of channels. If team_id provided, gets channels for that team.

    :param team_id: Optional team ID to filter channels
    :param include_deleted: Include deleted channels in results
    :return: JSON with list of channels or error
    """
    try:
        from open_webui.env import MATTERMOST_URL, MATTERMOST_TOKEN
        import aiohttp

        if not MATTERMOST_TOKEN:
            return json.dumps({"error": "Mattermost token not configured."})

        headers = {
            "Authorization": f"Bearer {MATTERMOST_TOKEN}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            if team_id:
                # Get channels for specific team
                url = f"{MATTERMOST_URL}/api/v4/teams/{team_id}/channels"
                params = {"include_deleted": "true" if include_deleted else "false"}

                async with session.get(url, headers=headers, params=params,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        channels = await response.json()
                        return json.dumps({
                            "channels": [{
                                "id": c["id"],
                                "team_id": c["team_id"],
                                "name": c["name"],
                                "display_name": c["display_name"],
                                "type": c["type"],
                                "header": c.get("header", ""),
                                "purpose": c.get("purpose", "")
                            } for c in channels]
                        }, ensure_ascii=False)
                    else:
                        error_text = await response.text()
                        return json.dumps({"error": f"Mattermost API error ({response.status}): {error_text}"})
            else:
                # Get user's channels across all teams
                url = f"{MATTERMOST_URL}/api/v4/users/me/channels"

                async with session.get(url, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        channels = await response.json()
                        return json.dumps({
                            "channels": [{
                                "id": c["id"],
                                "team_id": c["team_id"],
                                "name": c["name"],
                                "display_name": c["display_name"],
                                "type": c["type"]
                            } for c in channels]
                        }, ensure_ascii=False)
                    else:
                        error_text = await response.text()
                        return json.dumps({"error": f"Mattermost API error ({response.status}): {error_text}"})

    except Exception as e:
        log.exception(f"mattermost_get_channels error: {e}")
        return json.dumps({"error": str(e)})


async def mattermost_read_channel(
    channel_id: str,
    per_page: int = 60,
    since: Optional[int] = None,
    __request__=None,
    __user__=None,
) -> str:
    """
    Read messages from a Mattermost channel.

    :param channel_id: The ID of the channel to read from
    :param per_page: Number of posts to retrieve (default 60, max 200)
    :param since: Unix timestamp to get posts since (optional)
    :return: JSON with posts or error
    """
    try:
        from open_webui.env import MATTERMOST_URL, MATTERMOST_TOKEN
        import aiohttp

        if not MATTERMOST_TOKEN:
            return json.dumps({"error": "Mattermost token not configured."})

        headers = {
            "Authorization": f"Bearer {MATTERMOST_TOKEN}",
            "Content-Type": "application/json"
        }

        url = f"{MATTERMOST_URL}/api/v4/channels/{channel_id}/posts"
        params = {"per_page": min(per_page, 200)}
        if since:
            params["since"] = since

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params,
                                 timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    posts_list = []

                    # Posts are returned as a dict with post IDs as keys
                    # Order is in the 'order' array
                    for post_id in data.get("order", []):
                        post = data["posts"].get(post_id)
                        if post:
                            posts_list.append({
                                "id": post["id"],
                                "user_id": post["user_id"],
                                "channel_id": post["channel_id"],
                                "message": post["message"],
                                "created_at": post["create_at"],
                                "updated_at": post["update_at"]
                            })

                    return json.dumps({
                        "posts": posts_list,
                        "count": len(posts_list)
                    }, ensure_ascii=False)
                else:
                    error_text = await response.text()
                    return json.dumps({"error": f"Mattermost API error ({response.status}): {error_text}"})

    except Exception as e:
        log.exception(f"mattermost_read_channel error: {e}")
        return json.dumps({"error": str(e)})


async def mattermost_start_playbook(
    team_id: str,
    playbook_id: str,
    name: str,
    owner_user_id: str,
    description: str = "",
    __request__=None,
    __user__=None,
) -> str:
    """
    Start a playbook run in Mattermost.

    :param team_id: The team ID where the playbook run will be created
    :param playbook_id: The ID of the playbook to run
    :param name: Name for this playbook run
    :param owner_user_id: User ID who will own this run
    :param description: Optional description for the run
    :return: JSON with playbook run details or error
    """
    try:
        from open_webui.env import MATTERMOST_URL, MATTERMOST_TOKEN
        import aiohttp

        if not MATTERMOST_TOKEN:
            return json.dumps({"error": "Mattermost token not configured."})

        headers = {
            "Authorization": f"Bearer {MATTERMOST_TOKEN}",
            "Content-Type": "application/json"
        }

        url = f"{MATTERMOST_URL}/plugins/playbooks/api/v0/runs"
        data = {
            "team_id": team_id,
            "playbook_id": playbook_id,
            "name": name,
            "owner_user_id": owner_user_id,
            "description": description
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data,
                                  timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200 or response.status == 201:
                    result = await response.json()
                    return json.dumps({
                        "status": "success",
                        "run_id": result["id"],
                        "name": result["name"],
                        "channel_id": result.get("channel_id"),
                        "team_id": result["team_id"],
                        "playbook_id": result["playbook_id"],
                        "current_status": result.get("current_status", "in_progress")
                    }, ensure_ascii=False)
                else:
                    error_text = await response.text()
                    return json.dumps({"error": f"Mattermost Playbooks API error ({response.status}): {error_text}"})

    except Exception as e:
        log.exception(f"mattermost_start_playbook error: {e}")
        return json.dumps({"error": str(e)})


async def mattermost_check_playbook_status(
    run_id: str,
    __request__=None,
    __user__=None,
) -> str:
    """
    Check the status of a playbook run.

    :param run_id: The ID of the playbook run to check
    :return: JSON with playbook run status or error
    """
    try:
        from open_webui.env import MATTERMOST_URL, MATTERMOST_TOKEN
        import aiohttp

        if not MATTERMOST_TOKEN:
            return json.dumps({"error": "Mattermost token not configured."})

        headers = {
            "Authorization": f"Bearer {MATTERMOST_TOKEN}",
            "Content-Type": "application/json"
        }

        url = f"{MATTERMOST_URL}/plugins/playbooks/api/v0/runs/{run_id}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,
                                 timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    return json.dumps({
                        "run_id": result["id"],
                        "name": result["name"],
                        "current_status": result.get("current_status", "unknown"),
                        "is_active": result.get("is_active", False),
                        "team_id": result["team_id"],
                        "playbook_id": result["playbook_id"],
                        "channel_id": result.get("channel_id"),
                        "owner_user_id": result["owner_user_id"],
                        "create_at": result.get("create_at"),
                        "end_at": result.get("end_at")
                    }, ensure_ascii=False)
                else:
                    error_text = await response.text()
                    return json.dumps({"error": f"Mattermost Playbooks API error ({response.status}): {error_text}"})

    except Exception as e:
        log.exception(f"mattermost_check_playbook_status error: {e}")
        return json.dumps({"error": str(e)})


async def mattermost_check_playbook_runs(
    team_id: Optional[str] = None,
    playbook_id: Optional[str] = None,
    statuses: str = "",  # Comma-separated: InProgress,Finished
    owner_user_id: Optional[str] = None,
    participant_id: Optional[str] = None,
    per_page: int = 50,
    __request__=None,
    __user__=None,
) -> str:
    """
    Get a list of playbook runs with optional filters.

    :param team_id: Filter by team ID
    :param playbook_id: Filter by playbook ID
    :param statuses: Comma-separated list of statuses (InProgress,Finished)
    :param owner_user_id: Filter by owner user ID
    :param participant_id: Filter by participant user ID
    :param per_page: Number of results per page (default 50, max 200)
    :return: JSON with list of playbook runs or error
    """
    try:
        from open_webui.env import MATTERMOST_URL, MATTERMOST_TOKEN
        import aiohttp

        if not MATTERMOST_TOKEN:
            return json.dumps({"error": "Mattermost token not configured."})

        headers = {
            "Authorization": f"Bearer {MATTERMOST_TOKEN}",
            "Content-Type": "application/json"
        }

        url = f"{MATTERMOST_URL}/plugins/playbooks/api/v0/runs"
        params = {"per_page": min(per_page, 200)}

        if team_id:
            params["team_id"] = team_id
        if playbook_id:
            params["playbook_id"] = playbook_id
        if statuses:
            params["statuses"] = statuses
        if owner_user_id:
            params["owner_user_id"] = owner_user_id
        if participant_id:
            params["participant_id"] = participant_id

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params,
                                 timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    runs = data.get("items", [])

                    return json.dumps({
                        "runs": [{
                            "run_id": r["id"],
                            "name": r["name"],
                            "current_status": r.get("current_status", "unknown"),
                            "is_active": r.get("is_active", False),
                            "team_id": r["team_id"],
                            "playbook_id": r["playbook_id"],
                            "channel_id": r.get("channel_id"),
                            "owner_user_id": r["owner_user_id"],
                            "create_at": r.get("create_at")
                        } for r in runs],
                        "total_count": data.get("total_count", len(runs)),
                        "page_count": data.get("page_count", 1)
                    }, ensure_ascii=False)
                else:
                    error_text = await response.text()
                    return json.dumps({"error": f"Mattermost Playbooks API error ({response.status}): {error_text}"})

    except Exception as e:
        log.exception(f"mattermost_check_playbook_runs error: {e}")
        return json.dumps({"error": str(e)})


async def mattermost_end_playbook(
    run_id: str,
    __request__=None,
    __user__=None,
) -> str:
    """
    End (finish) a playbook run.

    :param run_id: The ID of the playbook run to end
    :return: JSON with success status or error
    """
    try:
        from open_webui.env import MATTERMOST_URL, MATTERMOST_TOKEN
        import aiohttp

        if not MATTERMOST_TOKEN:
            return json.dumps({"error": "Mattermost token not configured."})

        headers = {
            "Authorization": f"Bearer {MATTERMOST_TOKEN}",
            "Content-Type": "application/json"
        }

        url = f"{MATTERMOST_URL}/plugins/playbooks/api/v0/runs/{run_id}/finish"

        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=headers,
                                 timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return json.dumps({
                        "status": "success",
                        "run_id": run_id,
                        "message": "Playbook run ended successfully"
                    }, ensure_ascii=False)
                else:
                    error_text = await response.text()
                    return json.dumps({"error": f"Mattermost Playbooks API error ({response.status}): {error_text}"})

    except Exception as e:
        log.exception(f"mattermost_end_playbook error: {e}")
        return json.dumps({"error": str(e)})
