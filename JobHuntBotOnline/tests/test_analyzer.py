from datetime import date

from app.models import CandidateProfile, Experience, Job, Resume, json_dumps
from app.services.analyzer import analyse_job


def profile(**overrides):
    base = dict(
        id=1,
        user_id=1,
        preferred_name="Linze",
        email="linze@example.com",
        current_location="Sydney",
        work_authorization_text="Unrestricted Australian working rights",
        sponsorship_now=False,
        sponsorship_future=False,
        target_roles_json=json_dumps(["Data Analyst"]),
        secondary_roles_json="[]",
        roles_to_avoid_json="[]",
        industries_to_avoid_json="[]",
        target_locations_json=json_dumps(["Sydney"]),
        work_mode="Hybrid / Onsite / Remote",
        target_level="Graduate / Entry level",
        graduation_year="2027",
        professional_experience_years=1,
    )
    base.update(overrides)
    return CandidateProfile(**base)


def resume():
    return Resume(
        id=1,
        user_id=1,
        label="Data",
        role_family="Data Analyst",
        source_filename="resume.txt",
        file_type="txt",
        extracted_text="Python SQL Excel Power BI data analysis communication",
        skills_json=json_dumps(["Python", "SQL", "Excel", "Power BI", "Data Analysis", "Communication"]),
        is_default=True,
    )


def job(description: str):
    return Job(
        id=1,
        user_id=1,
        company="Example",
        title="Graduate Data Analyst",
        location="Sydney",
        posted_date="2026-08-08",
        description=description,
    )


def experience():
    return Experience(id=1, user_id=1, title="Data Analyst Intern", description="Used Python SQL and Power BI", tags_json=json_dumps(["Python", "SQL", "Power BI"]))


def test_matching_job_is_recommended():
    result = analyse_job(
        profile=profile(),
        job=job("Graduate role using Python SQL Excel and Power BI. Applicants need full Australian working rights."),
        resumes=[resume()],
        experiences=[experience()],
        today=date(2026, 8, 9),
    )
    assert result.recommendation == "Apply"
    assert result.fit_label in {"High", "Medium"}
    assert result.eligibility_status == "Eligible"
    assert result.selected_resume_id == 1


def test_sponsorship_conflict_is_hard_skip():
    result = analyse_job(
        profile=profile(sponsorship_future=True, work_authorization_text="Student visa"),
        job=job("Python SQL role. No visa sponsorship is available."),
        resumes=[resume()],
        experiences=[experience()],
        today=date(2026, 8, 9),
    )
    assert result.recommendation == "Skip"
    assert result.eligibility_status == "Ineligible"
    assert any("Sponsorship" in item for item in result.risks)


def test_unknown_work_rights_needs_user():
    result = analyse_job(
        profile=profile(work_authorization_text="", sponsorship_now=None, sponsorship_future=None),
        job=job("Applicants must have unrestricted Australian working rights."),
        resumes=[resume()],
        experiences=[experience()],
        today=date(2026, 8, 9),
    )
    assert result.recommendation == "Needs user"
    assert result.eligibility_status == "Needs confirmation"
