"""Pydantic schema for resume analysis JSON (Gemini structured output + validation)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_EVIDENCE_ROWS = 18
MAX_SKILL_ROADMAPS = 8
MAX_IMPROVED_BULLETS = 8
MAX_WEAK_SECTIONS = 10
MAX_IMPROVEMENT_SUGGESTIONS = 10
MAX_RECOMMENDED_KEYWORDS = 20
MAX_MATCHED_SKILLS = 15
MAX_MISSING_SKILLS = 15
MAX_PRIORITY_ACTIONS = 8


class SectionScores(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skills: int = Field(default=0, ge=0, le=100)
    experience: int = Field(default=0, ge=0, le=100)
    projects: int = Field(default=0, ge=0, le=100)
    format: int = Field(default=0, ge=0, le=100)


class ImprovedBullet(BaseModel):
    model_config = ConfigDict(extra="ignore")

    original: str = ""
    improved: str = ""


class PerSectionNotes(BaseModel):
    model_config = ConfigDict(extra="ignore")

    projects: str = ""
    internships: str = ""
    certifications: str = ""
    technical_skills: str = ""
    education: str = ""
    links_github_linkedin: str = ""


class FresherInsights(BaseModel):
    model_config = ConfigDict(extra="ignore")

    profile_type: Literal["student", "fresher", "internship_candidate", "general"] = (
        "general"
    )
    strongest_section: str = ""
    strongest_section_why: str = ""
    experience_substitute: str = ""
    per_section_notes: PerSectionNotes = Field(default_factory=PerSectionNotes)
    priority_actions: list[str] = Field(default_factory=list, max_length=MAX_PRIORITY_ACTIONS)


class EvidenceMatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requirement: str = ""
    match_status: Literal["yes", "weak", "no"] = "no"
    resume_evidence: str = ""
    where_in_resume: str = ""


class MiniProject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = ""
    description: str = ""
    suggested_stack: list[str] = Field(default_factory=list, max_length=12)
    demo_idea: str = ""


class SkillGapRoadmap(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skill_or_requirement: str = ""
    why_it_matters_for_this_role: str = ""
    learning_plan: list[str] = Field(
        default_factory=list,
        min_length=3,
        max_length=7,
    )
    mini_project: MiniProject = Field(default_factory=MiniProject)
    honest_resume_bullet_after_completion: str = ""


class ATSResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ats_score: int = Field(default=0, ge=0, le=100)
    section_scores: SectionScores = Field(default_factory=SectionScores)
    overall_feedback: str = ""
    matched_skills: list[str] = Field(default_factory=list, max_length=MAX_MATCHED_SKILLS)
    missing_skills: list[str] = Field(default_factory=list, max_length=MAX_MISSING_SKILLS)
    weak_sections: list[str] = Field(default_factory=list, max_length=MAX_WEAK_SECTIONS)
    improvement_suggestions: list[str] = Field(
        default_factory=list, max_length=MAX_IMPROVEMENT_SUGGESTIONS
    )
    recommended_keywords: list[str] = Field(
        default_factory=list, max_length=MAX_RECOMMENDED_KEYWORDS
    )
    rewritten_summary: str = ""
    improved_bullets: list[ImprovedBullet] = Field(
        default_factory=list, max_length=MAX_IMPROVED_BULLETS
    )
    final_recommendation: str = ""
    fresher_insights: FresherInsights = Field(default_factory=FresherInsights)
    evidence_matches: list[EvidenceMatch] = Field(
        default_factory=list, max_length=MAX_EVIDENCE_ROWS
    )
    skill_gap_roadmaps: list[SkillGapRoadmap] = Field(
        default_factory=list, max_length=MAX_SKILL_ROADMAPS
    )


def ats_result_json_schema() -> dict:
    """JSON Schema from Pydantic (for tooling/tests; Gemini calls omit response_schema)."""
    return ATSResult.model_json_schema()
