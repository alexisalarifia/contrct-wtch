from tracker import runner


def test_keep_rules():
    assert runner.keep({"naics": "336414", "office_name": "FA8609 AFLCMC WLCK KC46"})
    assert runner.keep({"naics": "541715", "psc": "AR12", "office_name": None})
    assert runner.keep({"naics": "541715", "psc": "AC13", "office_code": "FA2518", "office_name": "FA2518 USSF SPOC/SAIO", "sub_agency": "Department of the Air Force"})
    assert runner.keep({"naics": "541715", "psc": "AC13", "office_name": None, "sub_agency": "National Aeronautics and Space Administration"})
    assert runner.keep({"naics": "541715", "psc": "AC13", "office_name": "DEF ADVANCED RESEARCH PROJECTS AGCY"})
    assert not runner.keep({"naics": "541715", "psc": "AC13", "office_code": "FA8609", "office_name": "FA8609 AFLCMC WLCK KC46", "sub_agency": "Department of the Air Force"})
    assert runner.keep({"source": "sbir", "naics": None})
