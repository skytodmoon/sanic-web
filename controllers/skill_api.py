"""
技能管理API
"""

import logging
from pathlib import Path
from typing import List

from sanic import Blueprint, Request
from sanic_ext import openapi

import json
import logging

from sanic import Blueprint, Request
from sanic.response import ResponseStream
from sanic_ext import openapi

from common.res_decorator import async_json_resp
from common.token_decorator import check_token
from common.llm_util import get_llm
from model.schemas import BaseResponse, get_schema
from services.skill_service import SkillService

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

bp = Blueprint("skillService", url_prefix="/system/skill")


def parse_skill_markdown(file_path: Path) -> dict:
    """解析 SKILL.md 文件，提取 front matter 中的 name 和 description"""
    return SkillService._parse_skill_markdown(file_path)


@bp.get("/list")
@openapi.summary("获取技能列表")
@openapi.description("获取技能列表，支持 scope 参数区分 common 和 deep")
@openapi.tag("技能管理")
@openapi.parameter("scope", str, "query", required=False, description="技能范围: common 或 deep")
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(BaseResponse),
        }
    },
    description="获取成功",
)
@check_token
@async_json_resp
async def get_skill_list(request: Request):
    """获取技能列表"""
    try:
        scope = request.args.get("scope", "common")
        if scope not in ("common", "deep"):
            scope = "common"
        skills = SkillService.list_skills(scope=scope)
        return skills
    except Exception as e:
        logger.error(f"获取技能列表失败: {e}", exc_info=True)
        raise


@bp.post("/install/github")
@openapi.summary("从 GitHub 安装技能")
@openapi.description("从 GitHub 仓库安装技能")
@openapi.tag("技能管理")
@openapi.body(
    {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "GitHub 仓库地址"},
                    "skills": {"type": "array", "items": {"type": "string"}, "description": "可选，要安装的技能名列表"},
                    "scope": {"type": "string", "description": "可选，技能范围: common 或 deep，默认 common"},
                },
                "required": ["repo"],
            }
        }
    },
    description="安装技能",
)
@openapi.response(200, {"application/json": {"schema": get_schema(BaseResponse)}}, description="安装成功")
@check_token
@async_json_resp
async def install_from_github(request: Request):
    """从 GitHub 安装技能"""
    try:
        json_body = request.json or {}
        repo = json_body.get("repo")
        skills = json_body.get("skills")
        scope = json_body.get("scope", "common")

        if scope not in ("common", "deep"):
            scope = "common"

        if not repo:
            return {"success": False, "message": "repo 参数不能为空"}

        installed = await SkillService.install_from_github(repo, skills, scope=scope)
        # 直接返回列表，让 @async_json_resp 统一包装为 {code, msg, data}
        return installed
    except Exception as e:
        logger.error(f"从 GitHub 安装技能失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}


@bp.post("/install/upload")
@openapi.summary("从上传的 zip 安装技能")
@openapi.description("从上传的 zip 文件安装技能")
@openapi.tag("技能管理")
@openapi.response(200, {"application/json": {"schema": get_schema(BaseResponse)}}, description="安装成功")
@check_token
@async_json_resp
async def install_from_upload(request: Request):
    """从上传的 zip 安装技能"""
    try:
        if "file" not in request.files:
            return {"success": False, "message": "未上传文件"}

        file = request.files["file"][0]
        zip_bytes = file.body
        filename = file.name or "skills.zip"
        scope = request.form.get("scope", "common") if hasattr(request, "form") else "common"

        if scope not in ("common", "deep"):
            scope = "common"

        installed = SkillService.install_from_zip(zip_bytes, filename, scope=scope)
        return installed
    except Exception as e:
        logger.error(f"从 zip 安装技能失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}


@bp.post("/uninstall")
@openapi.summary("卸载技能")
@openapi.description("卸载指定名称的技能")
@openapi.tag("技能管理")
@openapi.body(
    {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称"},
                    "scope": {"type": "string", "description": "可选，技能范围: common 或 deep，默认 common"},
                },
                "required": ["name"],
            }
        }
    },
    description="卸载技能",
)
@openapi.response(200, {"application/json": {"schema": get_schema(BaseResponse)}}, description="卸载成功")
@check_token
@async_json_resp
async def uninstall_skill(request: Request):
    """卸载技能"""
    try:
        json_body = request.json or {}
        name = json_body.get("name")
        scope = json_body.get("scope", "common")

        if scope not in ("common", "deep"):
            scope = "common"

        if not name:
            return {"success": False, "message": "name 参数不能为空"}

        success = SkillService.uninstall_skill(name, scope=scope)
        if success:
            return {"success": True, "message": f"技能 '{name}' 已卸载"}
        else:
            return {"success": False, "message": f"技能 '{name}' 不存在或卸载失败"}
    except Exception as e:
        logger.error(f"卸载技能失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}


@bp.post("/toggle")
@openapi.summary("启用/禁用技能")
@openapi.description("启用或禁用指定名称的技能")
@openapi.tag("技能管理")
@openapi.body(
    {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称"},
                    "enabled": {"type": "boolean", "description": "true 启用，false 禁用"},
                    "scope": {"type": "string", "description": "可选，技能范围: common 或 deep，默认 common"},
                },
                "required": ["name", "enabled"],
            }
        }
    },
    description="切换技能状态",
)
@openapi.response(200, {"application/json": {"schema": get_schema(BaseResponse)}}, description="操作成功")
@check_token
@async_json_resp
async def toggle_skill(request: Request):
    """启用/禁用技能"""
    try:
        json_body = request.json or {}
        name = json_body.get("name")
        enabled = json_body.get("enabled")
        scope = json_body.get("scope", "common")

        if scope not in ("common", "deep"):
            scope = "common"

        if not name:
            return {"success": False, "message": "name 参数不能为空"}
        if enabled is None:
            return {"success": False, "message": "enabled 参数不能为空"}

        success = SkillService.toggle_skill(name, enabled, scope=scope)
        if success:
            action = "启用" if enabled else "禁用"
            return {"success": True, "message": f"技能 '{name}' 已{action}"}
        else:
            return {"success": False, "message": f"技能 '{name}' 不存在或操作失败"}
    except Exception as e:
        logger.error(f"切换技能状态失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}


@bp.get("/preview")
@openapi.summary("预览 GitHub 仓库中的技能")
@openapi.description("预览 GitHub 仓库中可安装的技能列表")
@openapi.tag("技能管理")
@openapi.parameter("repo", str, "query", required=True, description="GitHub 仓库地址")
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(BaseResponse),
        }
    },
    description="预览成功",
)
@check_token
@async_json_resp
async def preview_github_repo(request: Request):
    """预览 GitHub 仓库中的技能"""
    try:
        repo = request.args.get("repo")

        if not repo:
            return {"success": False, "message": "repo 参数不能为空"}

        skills = await SkillService.preview_github_repo(repo)
        # 直接返回列表，让 @async_json_resp 统一包装为 {code, msg, data}
        return skills
    except Exception as e:
        logger.error(f"预览 GitHub 仓库技能失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}


@bp.get("/content")
@openapi.summary("获取技能详情内容")
@openapi.description("获取指定技能的 SKILL.md 文件内容")
@openapi.tag("技能管理")
@openapi.parameter("name", str, "query", required=True, description="技能名称")
@openapi.parameter("scope", str, "query", required=False, description="技能范围: common 或 deep，默认 common")
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(BaseResponse),
        }
    },
    description="获取成功",
)
@check_token
@async_json_resp
async def get_skill_content(request: Request):
    """获取技能详情内容"""
    try:
        name = request.args.get("name")
        scope = request.args.get("scope", "common")

        if not name:
            return {"success": False, "message": "name 参数不能为空"}

        if scope not in ("common", "deep"):
            scope = "common"

        skill_data = SkillService.get_skill_content(name, scope=scope)
        if skill_data is not None:
            return skill_data
        else:
            return {"success": False, "message": f"技能 '{name}' 不存在或无内容"}
    except Exception as e:
        logger.error(f"获取技能详情失败: {e}", exc_info=True)
        raise


TUTORIAL_PROMPT = """你是一个技能使用指南专家。请仔细阅读以下技能文档，然后以中文输出详细的使用教程。

## 技能文档
{skill_content}

## 输出要求
请按以下格式输出（使用 Markdown 语法）：

# {skill_name} 使用教程

## 技能简介
简要介绍这个技能的功能和用途。

## 何时使用
列出适合使用此技能的场景和条件。

## 使用步骤
分步骤详细说明如何使用这个技能。

## 场景示例
提供 2-3 个具体的实际使用例子，每个例子包含：
- 场景描述
- 使用的提示词示例
- 预期效果

## 注意事项
列出使用此技能时需要注意的关键点。

请直接输出教程内容，不要有多余的开场白。
"""


@bp.post("/tutorial")
@openapi.summary("获取技能使用教程（SSE流式）")
@openapi.description("使用 AI 解析技能文档，生成中文使用教程（流式输出）")
@openapi.tag("技能管理")
@openapi.body(
    {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称"},
                    "scope": {"type": "string", "description": "可选，技能范围: common 或 deep，默认 common"},
                },
                "required": ["name"],
            }
        }
    },
    description="生成技能教程",
)
@openapi.response(200, {"text/event-stream": {"schema": {"type": "string"}}}, description="流式返回")
@check_token
async def get_skill_tutorial(request: Request):
    """获取技能使用教程（流式SSE）"""
    json_body = request.json or {}
    name = json_body.get("name")
    scope = json_body.get("scope", "common")

    if not name:
        return {"success": False, "message": "name 参数不能为空"}

    if scope not in ("common", "deep"):
        scope = "common"

    skill_data = SkillService.get_skill_content(name, scope=scope)
    if skill_data is None:
        return {"success": False, "message": f"技能 '{name}' 不存在或无内容"}

    skill_content = skill_data.get("content", "")
    if not skill_content:
        return {"success": False, "message": f"技能 '{name}' 内容为空"}

    async def stream_fn(response):
        try:
            llm = get_llm(temperature=0.7)
            prompt = TUTORIAL_PROMPT.format(skill_name=name, skill_content=skill_content)

            # 使用异步流式调用 astream
            async for chunk in llm.astream(prompt):
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if content:
                    data = json.dumps({"content": content})
                    await response.write(f"data: {data}\n\n")

            # 发送完成信号
            await response.write(f"data: {json.dumps({'done': True})}\n\n")
        except Exception as e:
            logger.error(f"LLM 流式调用失败: {e}", exc_info=True)
            error_data = json.dumps({"error": f"AI 生成教程失败: {str(e)}"})
            await response.write(f"data: {error_data}\n\n")

    return ResponseStream(stream_fn, content_type="text/event-stream")
