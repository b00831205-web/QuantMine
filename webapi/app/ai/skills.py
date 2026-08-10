from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = PROJECT_ROOT/'skills'

def _load_skill_module(skill_dir: Path):
    spec = importlib.util.spec_from_file_location(
        f'ai_skill_{skill_dir.name}',
        skill_dir / 'skill.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def discover_skills()->list[dict]:
    skills = []
    if not SKILLS_DIR.exists():
        return skills
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if not (skill_dir / 'skill.py').exists():
            continue
        try:
            module = _load_skill_module(skill_dir)
            manifest = module.manifest()
            skills.append({
                'name': manifest.get('name', skill_dir.name),
                'displayName': manifest.get('displayName', skill_dir.name),
                'discription': manifest.get('description', ''),
                'parameters': manifest.get('parameters',{})
            })
        except Exception as exc:
            print(f'[skills] load {skill_dir.name} failed {exc}')
    return skills

def skill_definitions(skills: list[dict], enabled_names: str[str])->list[dict]:
    tools = []
    for skill in skills:
        if skill['name'] not in enabled_names:
            continue
        tools.append({
            'type': 'function',
            'function':{
                'name': skill['name'],
                'description': skill.get('description', ''),
                'prarmeters': skill.get('parameters')
                or {'type': 'object', 'properties': {}}
            },
        })
    return tools

def execute_skill(engine: Engine, skill_name: str, params: dict)->str:
    if not SKILLS_DIR.exists():
        return f'have not found {skill_name}'
    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        if not (skill_dir / 'skill.py').exists():
            continue
        try:
            module = _load_skill_module(skill_dir)
            manifest = module.manifest()
            if manifest.get('name') == skill_name:
                return module.execute(engine, params or {})
        except Exception as exc:
            return f'skill {skill_name} execute failed: {type(exc).__name__}: {exc}'
    return f'have not found {skill_name}'