# app/models/job_posting.py
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class ExperienceRequirement:
    required: bool = True
    min: Optional[int] = None
    max: Optional[int] = None
    freshers_can_apply: bool = False


@dataclass
class AgeRange:
    min: Optional[int] = None
    max: Optional[int] = None


@dataclass
class SalaryRange:
    type: str = "Negotiable"
    min: Optional[int] = None
    max: Optional[int] = None


@dataclass
class CompensationBenefits:
    benefits: List[str] = field(default_factory=list)
    lunch_facility: Optional[str] = None
    salary_review: Optional[str] = None
    festival_bonus: Optional[str] = None
    other_benefits: Optional[str] = None


@dataclass
class HRContact:
    name: str
    designation: str
    email: str
    mobile: str


@dataclass
class JobPosting:
    """Typed model for a single bdjobs job circular.

    JobPoster's fill_* methods were built and tested against a plain dict
    shaped like bdjobs' own form fields (job_data.get("title"),
    job_data.get("experience") -> {"min": ..., "max": ...}, etc). Rather than
    rewriting that already-working Playwright logic to consume a dataclass
    directly, this model gives callers a typed, IDE-autocompletable,
    validated-by-construction way to build the data, then flattens back to
    that exact dict shape via `to_legacy_dict()`.
    """

    job_id: str
    title: str
    category: str
    vacancies: int
    employment_status: str
    workplace: str
    deadline: str
    education_level: str
    degree_level: str
    degree_title: str
    experience: ExperienceRequirement
    age: AgeRange
    gender: str
    preferred_industries: List[str]
    skills: List[str]
    job_responsibilities: str
    additional_requirements: str
    salary: SalaryRange
    compensation_benefits: CompensationBenefits
    job_location: str
    hr_contact: HRContact

    # Kept for reference/context - see main.py's original comment: no
    # fill_* step wires these to a real form input yet.
    specialization: Optional[str] = None
    resume_receiver_email: Optional[str] = None
    job_context: Optional[str] = None

    restrict_age: bool = False
    restrict_gender: bool = False
    restrict_experience: bool = False

    def to_legacy_dict(self) -> dict:
        """Flattens this model into the dict shape JobPoster's fill_* methods expect."""
        return {
            "job_id": self.job_id,
            "title": self.title,
            "category": self.category,
            "specialization": self.specialization,
            "vacancies": self.vacancies,
            "employment_status": self.employment_status,
            "workplace": self.workplace,
            "deadline": self.deadline,
            "resume_receiver_email": self.resume_receiver_email,
            "education_level": self.education_level,
            "degree_level": self.degree_level,
            "degree_title": self.degree_title,
            "experience": asdict(self.experience),
            "age": asdict(self.age),
            "gender": self.gender,
            "preferred_industries": list(self.preferred_industries),
            "skills": list(self.skills),
            "job_context": self.job_context,
            "job_responsibilities": self.job_responsibilities,
            "additional_requirements": self.additional_requirements,
            "salary": asdict(self.salary),
            "compensation_benefits": asdict(self.compensation_benefits),
            "job_location": self.job_location,
            "restrict_age": self.restrict_age,
            "restrict_gender": self.restrict_gender,
            "restrict_experience": self.restrict_experience,
            "hr_contact": asdict(self.hr_contact),
        }