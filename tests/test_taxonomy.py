from tracker import taxonomy


def test_multi_label_and_primary_order():
    primary, tags = taxonomy.tag_award({"description": "SATELLITE BUS WITH ELECTRIC PROPULSION AND 3D PRINTED TITANIUM TANK"})
    assert primary == "Propulsion"
    assert "Advanced Materials & Manufacturing" in tags
    assert "Guided Missile & Space Vehicle" in tags


def test_naics_description_contributes():
    primary, tags = taxonomy.tag_award({"description": "ENGINEERING AND MANUFACTURING DEVELOPMENT", "naics_desc": "GUIDED MISSILE AND SPACE VEHICLE MANUFACTURING"})
    assert primary == "Guided Missile & Space Vehicle"


def test_uncategorized():
    assert taxonomy.tag_award({"description": "KC-X MODERNIZATION PROGRAM"}) == ("Uncategorized", ["Uncategorized"])
    assert taxonomy.categorize_abstract("") == "Uncategorized"


def test_engine_does_not_match_engineering():
    assert "Propulsion" not in taxonomy.tag_text("ENGINEERING SERVICES")
    assert "Propulsion" in taxonomy.tag_text("ROCKET ENGINE TEST")


def test_generic_tags_ignore_code_descriptions():
    primary, tags = taxonomy.tag_award({"description": "LOGISTICS SUPPORT", "psc_desc": "NATIONAL DEFENSE R&D SERVICES; APPLIED RESEARCH"})
    assert primary == "Uncategorized"
    primary, tags = taxonomy.tag_award({"description": "APPLIED RESEARCH IN WIDGETS", "psc_desc": "R&D"})
    assert tags == ["Research & Development (general)"]


def test_lane_and_new_tags():
    assert taxonomy.lane_for({"naics": "541715", "psc": "AR12"}) == "Space R&D services (PSC AR)"
    assert taxonomy.lane_for({"naics": "336414", "psc": "AC13"}) == "Space vehicles & parts (NAICS 3364xx)"
    assert taxonomy.lane_for({"naics": "541330", "psc": "R425"}) == "Engineering & technical support (PSC R4)"
    assert taxonomy.lane_for({}) == "Other"
    assert taxonomy.tag_award({"description": "SCALABLE HOMELAND INNOVATIVE ENTERPRISE LAYERED DEFENSE (SHIELD) INITIAL ORDER."})[0] == "Missile Defense"
    assert "Autonomy & AI" in taxonomy.tag_text("JARVIS - AGENTIC AI FOR SENSOR FUSION")


def test_human_spaceflight():
    assert taxonomy.tag_award({"description": "TAS DESIGN, DEVELOPMENT, TEST&EVALUATION OF PROJECT ORION"})[0] == "Human Spaceflight & Exploration"


def test_command_breakout():
    assert taxonomy.command_for({"office_code": "FA8818", "office_name": "FA8818  SSC/AAK-KT", "award_id": "FA881826C0001", "sub_agency": "Department of the Air Force"}) == "Space Force / SSC"
    assert taxonomy.command_for({"award_id": "HQ085126FE029", "office_name": "MISSILE DEFENSE AGENCY (MDA)"}) == "MDA"
    assert taxonomy.command_for({"award_id": "HQ085026C0001", "office_name": None, "sub_agency": "Department of the Air Force"}) == "Space Force / SDA"
    assert taxonomy.command_for({"award_id": "FA251826F0001", "office_name": "FA2518 USSF SPOC/SAIO"}) == "Space Force / other"
    assert taxonomy.command_for({"award_id": "FA880926C0001", "office_name": "FA8809 SDA AND CMBT PWR SSC/SZK-IK"}) == "Space Force / SSC"
    assert taxonomy.command_for({"award_id": "FA240126F0001", "office_name": "FA2401 SPACE DEVELOPMENT AGENCY SDA"}) == "Space Force / SDA"
    assert taxonomy.command_for({"award_id": "FA865026C0001", "office_name": "FA2385 USAF AFMC AFRL PZL AFRL RSKD"}) == "AFRL / AFWERX / SBIR"
    assert taxonomy.command_for({"award_id": "80NSSC26K0001", "office_name": None, "sub_agency": "National Aeronautics and Space Administration"}) == "NASA"
    assert taxonomy.command_for({"award_id": "FA860926FB002", "office_name": "FA8609 AFLCMC WLCK KC46", "sub_agency": "Department of the Air Force"}) == "AFLCMC"
