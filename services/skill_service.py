"""
技能管理核心服务
"""

import logging
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List

import httpx
import yaml

logger = logging.getLogger(__name__)


class SkillService:
    """技能管理服务"""

    # 两个技能目录
    COMMON_SKILLS_DIR = Path(__file__).parent.parent / "agent" / "common" / "skills"
    DEEP_SKILLS_DIR = Path(__file__).parent.parent / "agent" / "deepagent" / "skills"

    @classmethod
    def get_skills_dir(cls, scope: str = "common") -> Path:
        """获取技能目录"""
        if scope == "deep":
            return cls.DEEP_SKILLS_DIR
        return cls.COMMON_SKILLS_DIR

    @classmethod
    def list_skills(cls, scope: str = "common") -> list[dict]:
        """列出已安装技能及状态，scope=common 或 deep"""
        skills_dir = cls.get_skills_dir(scope)
        skills = []

        if not skills_dir.exists() or not skills_dir.is_dir():
            return skills

        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skill_info = cls._parse_skill_markdown(skill_file)
                    skill_info["path"] = str(skill_dir)
                    # 检查是否被禁用
                    skill_info["enabled"] = not (skill_dir / ".disabled").exists()
                    skills.append(skill_info)

        skills.sort(key=lambda x: x["name"])
        return skills

    @classmethod
    def _parse_skill_markdown(cls, file_path: Path) -> dict:
        """解析 SKILL.md 文件，提取 front matter 中的 name 和 description"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 解析 YAML front matter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    front_matter = parts[1].strip()
                    # 用 yaml.safe_load 正确解析多行 description (">" 折叠语法)
                    try:
                        meta = yaml.safe_load(front_matter)
                    except yaml.YAMLError:
                        # YAML 解析失败时（如 description 包含未转义的冒号），
                        # 使用正则表达式提取 name 和 description
                        meta = None
                        name_match = re.search(
                            r"^name:\s*(.+?)\s*$", front_matter, re.MULTILINE
                        )
                        desc_match = re.search(
                            r"^description:\s*(.+?)\s*$", front_matter, re.MULTILINE
                        )
                        if name_match or desc_match:
                            meta = {
                                "name": (
                                    name_match.group(1).strip() if name_match else None
                                ),
                                "description": (
                                    desc_match.group(1).strip() if desc_match else None
                                ),
                            }
                    if isinstance(meta, dict):
                        return {
                            "name": meta.get("name") or file_path.parent.name,
                            "description": meta.get("description") or "",
                        }
        except Exception as e:
            logger.error(f"解析技能文件失败 {file_path}: {e}")

        return {"name": file_path.parent.name, "description": ""}

    @classmethod
    async def install_from_github(
        cls, repo: str, skill_names: list[str] | None = None, scope: str = "common"
    ) -> list[dict]:
        """从 GitHub 仓库安装技能"""
        if scope not in ("common", "deep"):
            scope = "common"
        # 尝试 main 分支，失败则 master
        branches = ["main", "master"]
        downloaded_skills = []
        temp_dir = None

        for branch in branches:
            try:
                downloaded_skills, temp_dir = await cls._download_github_skills(
                    repo, branch, skill_names
                )
                break
            except Exception as e:
                logger.warning(f"从 {repo} ({branch} 分支) 下载技能失败: {e}")
                continue

        if not downloaded_skills:
            raise Exception(f"无法从 {repo} 下载技能，请检查仓库地址和分支")

        # 安装技能
        installed_skills = []
        for skill_info in downloaded_skills:
            try:
                success = cls._install_skill(skill_info, scope=scope)
                if success:
                    installed_skills.append(skill_info)
            except Exception as e:
                logger.error(f"安装技能 {skill_info.get('name')} 失败: {e}")

        # 安装完成后清理临时目录
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return installed_skills

    @classmethod
    async def _download_github_skills(
        cls, repo: str, branch: str, skill_names: list[str] | None = None
    ) -> tuple[list[dict], Path]:
        """从 GitHub 下载技能，返回 (skills列表, 临时目录)"""
        # 清理 repo 格式
        repo = repo.strip("/")
        if repo.startswith("https://github.com/"):
            repo = repo.replace("https://github.com/", "")
        elif repo.startswith("git@github.com:"):
            repo = repo.replace("git@github.com:", "")

        # 构建下载 URL
        zip_url = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"

        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            response = await client.get(zip_url)
            response.raise_for_status()
            skills, temp_dir = cls._extract_skills_from_zip(
                response.content, skill_names
            )

        return skills, temp_dir

    @classmethod
    def _extract_skills_from_zip(
        cls, zip_bytes: bytes, skill_names: list[str] | None = None
    ) -> tuple[list[dict], Path]:
        """从 zip 内容中提取技能信息，返回 (skills列表, 临时目录路径)"""
        temp_dir = Path(tempfile.mkdtemp())

        zip_path = temp_dir / "download.zip"
        with open(zip_path, "wb") as f:
            f.write(zip_bytes)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)

        # 递归扫描 SKILL.md 文件
        skills = []
        for skill_md in temp_dir.rglob("**/SKILL.md"):
            skill_dir = skill_md.parent
            skill_info = cls._parse_skill_markdown(skill_md)

            # 过滤技能名
            if skill_names and skill_info["name"] not in skill_names:
                continue

            # GitHub zip 解压后目录名带分支后缀（如 xxx-main, xxx-master）
            # 需要去除分支后缀后再比较
            expected_dir_name = skill_info["name"]
            actual_dir_name = skill_dir.name
            # 去掉常见的分支后缀再比较
            stripped_name = actual_dir_name
            for suffix in ["-main", "-master"]:
                if stripped_name.endswith(suffix):
                    stripped_name = stripped_name[: -len(suffix)]
            if stripped_name != expected_dir_name:
                logger.warning(
                    f"技能目录名 '{actual_dir_name}' (stripped: '{stripped_name}') "
                    f"与 SKILL.md 中的 name '{expected_dir_name}' 不一致，跳过"
                )
                continue

            # 修正目录名为正确的 skill name（用于后续拷贝）
            skill_info["source_dir"] = str(skill_dir)
            skill_info["correct_name"] = expected_dir_name
            skills.append(skill_info)

        return skills, temp_dir

    @classmethod
    def _setup_skill_venv(cls, skill_dir: Path) -> bool:
        """为 skill 创建独立虚拟环境并安装依赖"""
        requirements_file = skill_dir / "requirements.txt"
        if not requirements_file.exists():
            # 无 requirements.txt，跳过
            return True

        venv_dir = skill_dir / ".venv"
        try:
            # 创建虚拟环境
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )

            # 确定 pip 的路径（跨平台兼容）
            pip_path = (
                venv_dir / "bin" / "pip"
                if venv_dir.joinpath("bin").exists()
                else venv_dir / "Scripts" / "pip.exe"
            )

            # 安装依赖
            subprocess.run(
                [str(pip_path), "install", "-r", str(requirements_file), "-q"],
                check=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
            logger.info(f"技能 '{skill_dir.name}' 虚拟环境创建成功，依赖已安装")
            return True
        except subprocess.TimeoutExpired:
            logger.error(f"技能 '{skill_dir.name}' 虚拟环境创建超时")
            return False
        except Exception as e:
            logger.error(f"技能 '{skill_dir.name}' 创建虚拟环境失败: {e}")
            return False

    @classmethod
    def _install_skill(cls, skill_info: dict, scope: str = "common") -> bool:
        """安装单个技能"""
        source_dir = Path(skill_info["source_dir"])
        skill_name = skill_info.get("correct_name") or skill_info["name"]
        skills_dir = cls.get_skills_dir(scope)
        target_dir = skills_dir / skill_name

        # 验证源目录存在
        if not source_dir.exists():
            raise FileNotFoundError(f"技能源目录不存在: {source_dir}")

        # 如果已存在，先删除
        if target_dir.exists():
            shutil.rmtree(target_dir)

        # 确保目录存在
        skills_dir.mkdir(parents=True, exist_ok=True)

        # 复制技能目录
        shutil.copytree(source_dir, target_dir)

        # 自动创建虚拟环境
        cls._setup_skill_venv(target_dir)

        logger.info(f"技能 '{skill_name}' 安装成功到 {scope} 目录")
        return True

    @classmethod
    def install_from_zip(
        cls, zip_bytes: bytes, filename: str, scope: str = "common"
    ) -> list[dict]:
        """从 zip 安装"""
        if scope not in ("common", "deep"):
            scope = "common"
        temp_dir = Path(tempfile.mkdtemp())

        try:
            zip_path = temp_dir / "upload.zip"
            with open(zip_path, "wb") as f:
                f.write(zip_bytes)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_dir)

            # 扫描 SKILL.md 文件
            skills = []
            for skill_md in temp_dir.rglob("**/SKILL.md"):
                skill_dir = skill_md.parent
                skill_info = cls._parse_skill_markdown(skill_md)

                # 上传的 zip 包顶层目录是随机 temp 目录名，不是技能名
                # 只做一个 skill 且顶层目录是 temp 随机名时，直接使用
                actual_dir_name = skill_dir.name
                stripped_name = actual_dir_name
                for suffix in ["-main", "-master"]:
                    if stripped_name.endswith(suffix):
                        stripped_name = stripped_name[: -len(suffix)]

                # 检查是否只有一个 skill，且目录名不匹配（temp 目录情况）
                all_skill_mds = list(temp_dir.rglob("**/SKILL.md"))
                is_single_skill = len(all_skill_mds) == 1
                name_mismatch = stripped_name != skill_info["name"]

                if is_single_skill and name_mismatch:
                    # 单 skill 的 zip，顶层是随机 temp 目录，直接使用
                    logger.info(
                        f"检测到单技能 zip（temp 目录模式），技能名: {skill_info['name']}"
                    )
                elif stripped_name != skill_info["name"]:
                    logger.warning(
                        f"技能目录名 '{actual_dir_name}' 与 SKILL.md 中的 name '{skill_info['name']}' 不一致，跳过"
                    )
                    continue

                skill_info["source_dir"] = str(skill_dir)
                skill_info["correct_name"] = skill_info["name"]
                skills.append(skill_info)

            # 安装技能
            installed_skills = []
            for skill_info in skills:
                try:
                    success = cls._install_skill(skill_info, scope=scope)
                    if success:
                        installed_skills.append(skill_info)
                except Exception as e:
                    logger.error(f"安装技能 {skill_info.get('name')} 失败: {e}")

            # 安装完成后清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)

            return installed_skills

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @classmethod
    def uninstall_skill(cls, skill_name: str, scope: str = "common") -> bool:
        """卸载技能"""
        skills_dir = cls.get_skills_dir(scope)
        skill_dir = skills_dir / skill_name

        if not skill_dir.exists():
            logger.warning(f"技能 '{skill_name}' 不存在于 {scope} 目录")
            return False

        try:
            shutil.rmtree(skill_dir)
            logger.info(f"技能 '{skill_name}' 从 {scope} 目录卸载成功")
            return True
        except Exception as e:
            logger.error(f"卸载技能 '{skill_name}' 失败: {e}")
            return False

    @classmethod
    def toggle_skill(
        cls, skill_name: str, enabled: bool, scope: str = "common"
    ) -> bool:
        """启用/禁用技能"""
        skills_dir = cls.get_skills_dir(scope)
        skill_dir = skills_dir / skill_name
        disabled_file = skill_dir / ".disabled"

        if not skill_dir.exists():
            logger.warning(f"技能 '{skill_name}' 不存在于 {scope} 目录")
            return False

        try:
            if enabled:
                # 启用 - 删除 .disabled 文件
                if disabled_file.exists():
                    disabled_file.unlink()
                logger.info(f"技能 '{skill_name}' 已在 {scope} 目录启用")
            else:
                # 禁用 - 创建 .disabled 文件
                disabled_file.touch()
                logger.info(f"技能 '{skill_name}' 已在 {scope} 目录禁用")
            return True
        except Exception as e:
            logger.error(f"切换技能状态 '{skill_name}' 失败: {e}")
            return False

    @classmethod
    def get_enabled_skill_paths(
        cls, selected_skills: list[str] | None = None, scope: str = "common"
    ) -> list[str]:
        """获取生效的技能路径"""
        if selected_skills is not None:
            # 如果指定了技能列表，直接返回对应路径（忽略 .disabled）
            paths = []
            skills_dir = cls.get_skills_dir(scope)
            for skill_name in selected_skills:
                skill_dir = skills_dir / skill_name
                if skill_dir.exists():
                    paths.append(str(skill_dir))
            return paths

        # 如果没有指定，返回所有未禁用的技能
        enabled_paths = []
        for skill_info in cls.list_skills(scope=scope):
            if skill_info.get("enabled", True):
                enabled_paths.append(skill_info["path"])

        return enabled_paths

    @classmethod
    async def preview_github_repo(cls, repo: str) -> list[dict]:
        """预览 GitHub 仓库中的技能"""
        branches = ["main", "master"]
        temp_dir = None

        for branch in branches:
            try:
                skills, temp_dir = await cls._download_github_skills(repo, branch)
                if skills:
                    # 预览模式也需要清理临时目录
                    if temp_dir:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    return skills
            except Exception as e:
                logger.warning(f"预览 {repo} ({branch} 分支) 失败: {e}")
                continue

        return []

    @classmethod
    def get_skill_content(cls, skill_name: str, scope: str = "common") -> dict | None:
        """获取技能的 SKILL.md 内容（去除 front matter）"""
        skills_dir = cls.get_skills_dir(scope)
        skill_dir = skills_dir / skill_name
        skill_file = skill_dir / "SKILL.md"

        if not skill_file.exists():
            logger.warning(f"技能 '{skill_name}' 的 SKILL.md 不存在于 {scope} 目录")
            return None

        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()

            description = ""
            # 去除 YAML front matter 并提取 description
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    front_matter = parts[1].strip()
                    meta = yaml.safe_load(front_matter)
                    if isinstance(meta, dict):
                        description = meta.get("description") or ""
                    content = parts[2].strip()

            return {
                "name": skill_name,
                "description": description,
                "content": content,
            }
        except Exception as e:
            logger.error(f"读取技能文件失败 {skill_file}: {e}")
            return None
