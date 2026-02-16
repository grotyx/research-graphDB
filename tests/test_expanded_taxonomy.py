#!/usr/bin/env python3
"""Test script for expanded taxonomy entity normalization.

Verifies that new interventions, outcomes, and pathologies are correctly normalized.
"""

from src.graph.entity_normalizer import EntityNormalizer


def test_new_interventions():
    """Test new intervention normalization."""
    print("=" * 80)
    print("TESTING NEW INTERVENTIONS")
    print("=" * 80)

    normalizer = EntityNormalizer()

    test_cases = [
        # Motion Preservation
        ("Artificial Disc Replacement", "ADR"),
        ("TDR", "ADR"),
        ("Dynamic Stabilization", "Dynamic Stabilization"),
        ("Interspinous Device", "Interspinous Device"),
        ("IPD", "Interspinous Device"),

        # New Fusion Techniques
        ("Minimally Invasive TLIF", "MIS-TLIF"),
        ("MIS TLIF", "MIS-TLIF"),
        ("Cortical Bone Trajectory", "CBT Fusion"),
        ("CBT", "CBT Fusion"),
        ("C1-2 Fusion", "C1-C2 Fusion"),
        ("Atlantoaxial Fusion", "C1-C2 Fusion"),
        ("MIDLF", "MIDLF"),

        # New Decompression
        ("Percutaneous Endoscopic Lumbar Discectomy", "PELD"),
        ("PELD technique", "PELD"),
        ("Full Endoscopic Spinal Surgery", "FESS"),
        ("Microscopic Decompression", "Microdecompression"),
        ("Hemilaminotomy", "Laminotomy"),
        ("UBD", "UBD"),
        ("Over the top Decompression", "Over-the-top Decompression"),

        # Vertebral Augmentation
        ("Percutaneous Vertebroplasty", "PVP"),
        ("Vertebroplasty", "PVP"),
        ("Percutaneous Kyphoplasty", "PKP"),
        ("Balloon Kyphoplasty", "PKP"),

        # Osteotomy
        ("Three-Column Osteotomy", "COWO"),
        ("3-Column Osteotomy", "COWO"),
    ]

    passed = 0
    failed = 0

    for input_text, expected in test_cases:
        result = normalizer.normalize_intervention(input_text)
        status = "✅" if result.normalized == expected else "❌"

        if result.normalized == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status} '{input_text}' → '{result.normalized}' (expected: '{expected}', conf: {result.confidence:.2f})")

    print(f"\nIntervention Tests: {passed} passed, {failed} failed")
    assert failed == 0, f"{failed} intervention test cases failed"


def test_new_outcomes():
    """Test new outcome normalization."""
    print("\n" + "=" * 80)
    print("TESTING NEW OUTCOMES")
    print("=" * 80)

    normalizer = EntityNormalizer()

    test_cases = [
        # Pain Outcomes
        ("VAS-back", "VAS Back"),
        ("Back VAS", "VAS Back"),
        ("VAS leg pain", "VAS Leg"),
        ("Leg VAS", "VAS Leg"),
        ("Numeric Rating Scale", "NRS"),
        ("NRS score", "NRS"),

        # Functional Outcomes
        ("Neck Disability Index", "NDI"),
        ("NDI score", "NDI"),
        ("Modified JOA", "mJOA"),
        ("mJOA score", "mJOA"),

        # Radiological Outcomes
        ("Cage migration", "Cage Migration"),
        ("Subsidence", "Cage Subsidence"),
        ("Lumbar lordosis", "Lordosis"),
        ("LL", "Lordosis"),
        ("Pelvic Tilt", "PT"),
        ("PT angle", "PT"),

        # Complications
        ("Durotomy", "Dural Tear"),
        ("Incidental durotomy", "Dural Tear"),
        ("CSF leak", "Dural Tear"),
        ("Nerve root injury", "Nerve Injury"),
        ("Surgical site infection", "Infection Rate"),
        ("SSI", "Infection Rate"),
        ("Adjacent Segment Disease", "ASD"),
    ]

    passed = 0
    failed = 0

    for input_text, expected in test_cases:
        result = normalizer.normalize_outcome(input_text)
        status = "✅" if result.normalized == expected else "❌"

        if result.normalized == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status} '{input_text}' → '{result.normalized}' (expected: '{expected}', conf: {result.confidence:.2f})")

    print(f"\nOutcome Tests: {passed} passed, {failed} failed")
    assert failed == 0, f"{failed} outcome test cases failed"


def test_new_pathologies():
    """Test new pathology normalization."""
    print("\n" + "=" * 80)
    print("TESTING NEW PATHOLOGIES")
    print("=" * 80)

    normalizer = EntityNormalizer()

    test_cases = [
        # Degenerative
        ("Cervical Spinal Stenosis", "Cervical Stenosis"),
        ("CSS", "Cervical Stenosis"),
        ("Foraminal narrowing", "Foraminal Stenosis"),
        ("Cervical HNP", "Cervical Disc Herniation"),
        ("CDH", "Cervical Disc Herniation"),
        ("Degenerative Disc Disease", "DDD"),
        ("Disc Degeneration", "DDD"),
        ("Facet Joint Arthritis", "Facet Arthropathy"),

        # Deformity
        ("Adult Idiopathic Scoliosis", "Adult Scoliosis"),
        ("Adult Spinal Deformity", "ASD"),
        ("Flat Back Syndrome", "Flat Back"),
        ("Flatback", "Flat Back"),
        ("Sagittal malalignment", "Sagittal Imbalance"),

        # Trauma
        ("Flexion-distraction injury", "Chance Fracture"),
        ("Seatbelt injury", "Chance Fracture"),
        ("Fracture dislocation", "Fracture-Dislocation"),

        # Tumor
        ("Primary Spinal Tumor", "Primary Tumor"),
        ("Intradural neoplasm", "Intradural Tumor"),

        # Infection
        ("Discitis", "Spondylodiscitis"),
        ("Vertebral osteomyelitis", "Vertebral Osteomyelitis"),
        ("Spinal Epidural Abscess", "Epidural Abscess"),
        ("SEA", "Epidural Abscess"),
        ("Pott Disease", "Spinal TB"),
        ("Pott's disease", "Spinal TB"),
    ]

    passed = 0
    failed = 0

    for input_text, expected in test_cases:
        result = normalizer.normalize_pathology(input_text)
        status = "✅" if result.normalized == expected else "❌"

        if result.normalized == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status} '{input_text}' → '{result.normalized}' (expected: '{expected}', conf: {result.confidence:.2f})")

    print(f"\nPathology Tests: {passed} passed, {failed} failed")
    assert failed == 0, f"{failed} pathology test cases failed"


def test_extraction():
    """Test entity extraction from text."""
    print("\n" + "=" * 80)
    print("TESTING ENTITY EXTRACTION FROM TEXT")
    print("=" * 80)

    normalizer = EntityNormalizer()

    # Test intervention extraction
    text1 = "Comparison of MIS-TLIF and OLIF for treatment of lumbar stenosis with cage subsidence analysis"
    interventions = normalizer.extract_and_normalize_interventions(text1)
    outcomes = normalizer.extract_and_normalize_outcomes(text1)
    pathologies = normalizer.extract_and_normalize_pathologies(text1)

    print(f"\nText: '{text1}'")
    print(f"Interventions found: {[i.normalized for i in interventions]}")
    print(f"Outcomes found: {[o.normalized for o in outcomes]}")
    print(f"Pathologies found: {[p.normalized for p in pathologies]}")

    # Test mixed Korean/English
    text2 = "척추 감염 환자에서 PELD와 PVP 시술 후 VAS back pain 및 Infection Rate 평가"
    interventions2 = normalizer.extract_and_normalize_interventions(text2)
    outcomes2 = normalizer.extract_and_normalize_outcomes(text2)
    pathologies2 = normalizer.extract_and_normalize_pathologies(text2)

    print(f"\nText: '{text2}'")
    print(f"Interventions found: {[i.normalized for i in interventions2]}")
    print(f"Outcomes found: {[o.normalized for o in outcomes2]}")
    print(f"Pathologies found: {[p.normalized for p in pathologies2]}")

    # Verify expected results
    expected_checks = [
        (len(interventions) >= 2, "Should find at least 2 interventions in text1"),
        (any(i.normalized == "Lumbar Stenosis" for i in pathologies), "Should find Lumbar Stenosis in text1"),
        (any(o.normalized == "Cage Subsidence" for o in outcomes), "Should find Cage Subsidence in text1"),
        (len(interventions2) >= 2, "Should find at least 2 interventions in text2"),
    ]

    all_passed = True
    for check, description in expected_checks:
        status = "✅" if check else "❌"
        print(f"{status} {description}")
        if not check:
            all_passed = False

    assert all_passed, "One or more extraction checks failed"


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("EXPANDED TAXONOMY ENTITY NORMALIZATION TESTS")
    print("=" * 80 + "\n")

    results = []
    results.append(("Interventions", test_new_interventions()))
    results.append(("Outcomes", test_new_outcomes()))
    results.append(("Pathologies", test_new_pathologies()))
    results.append(("Extraction", test_extraction()))

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)

    if all_passed:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    exit(main())
