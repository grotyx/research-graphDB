#!/usr/bin/env python3
"""Test script for ImplantNode consolidation (v7.1).

Verifies that ImplantNode can represent both implants and instruments
with the new unified schema.
"""

from src.graph.spine_schema import ImplantNode

def test_implant_device():
    """Test creating an implant device."""
    implant = ImplantNode(
        name="Pedicle Screw",
        device_type="implant",
        implant_category="screw",
        material="titanium",
        is_permanent=True,
        is_reusable=False,
        fda_status="510k",
        fda_clearance_year=2015,
        manufacturer="Medtronic",
        product_name="CD Horizon Legacy",
        indicated_for=["lumbar fusion", "thoracic fixation"],
        contraindicated_for=["osteoporosis", "infection"],
        elastic_modulus="114 GPa",
        description="Polyaxial pedicle screw with titanium construction"
    )

    props = implant.to_neo4j_properties()
    print("Implant Device Properties:")
    for key, value in props.items():
        if value and value != 0 and value != [] and value != True:
            print(f"  {key}: {value}")

    # Test round-trip conversion
    restored = ImplantNode.from_neo4j_record(props)
    assert restored.name == "Pedicle Screw"
    assert restored.device_type == "implant"
    assert restored.is_permanent == True
    print("✓ Implant round-trip successful\n")


def test_instrument_device():
    """Test creating an instrument device."""
    instrument = ImplantNode(
        name="Kerrison Rongeur",
        device_type="instrument",
        instrument_category="cutting",
        material="stainless_steel",
        is_permanent=False,
        is_reusable=True,
        fda_status="approved",
        manufacturer="Aesculap",
        product_name="Kerrison Rongeur Standard",
        indicated_for=["laminectomy", "foraminotomy"],
        usage="Used for bone and ligament removal during decompression",
        description="Curved rongeur for bone removal"
    )

    props = instrument.to_neo4j_properties()
    print("Instrument Device Properties:")
    for key, value in props.items():
        if value and value != 0 and value != [] and value != False:
            print(f"  {key}: {value}")

    # Test round-trip conversion
    restored = ImplantNode.from_neo4j_record(props)
    assert restored.name == "Kerrison Rongeur"
    assert restored.device_type == "instrument"
    assert restored.is_permanent == False
    assert restored.is_reusable == True
    print("✓ Instrument round-trip successful\n")


def test_consumable_device():
    """Test creating a consumable device."""
    consumable = ImplantNode(
        name="Bone Graft Substitute",
        device_type="consumable",
        implant_category="graft",
        material="synthetic_calcium_phosphate",
        is_permanent=True,
        is_reusable=False,
        fda_status="510k",
        manufacturer="Medtronic",
        product_name="Mastergraft",
        indicated_for=["spinal fusion", "void filling"],
        description="Resorbable bone graft substitute"
    )

    props = consumable.to_neo4j_properties()
    print("Consumable Device Properties:")
    for key, value in props.items():
        if value and value != 0 and value != [] and value != True:
            print(f"  {key}: {value}")

    # Test round-trip conversion
    restored = ImplantNode.from_neo4j_record(props)
    assert restored.name == "Bone Graft Substitute"
    assert restored.device_type == "consumable"
    print("✓ Consumable round-trip successful\n")


def test_backward_compatibility():
    """Test backward compatibility with old 'category' field name."""
    # Simulate old database record with 'category' instead of 'implant_category'
    old_record = {
        "name": "PEEK Cage",
        "category": "cage",  # Old field name
        "material": "PEEK",
        "manufacturer": "Stryker",
        "fda_status": "approved",
        "description": "Interbody fusion cage"
    }

    # Should still work with from_neo4j_record (using defaults)
    implant = ImplantNode.from_neo4j_record(old_record)
    assert implant.name == "PEEK Cage"
    assert implant.device_type == "implant"  # Default value
    print("✓ Backward compatibility check passed\n")


def test_all_new_fields():
    """Test that all v7.1 fields are present."""
    required_fields = [
        'device_type', 'implant_category', 'instrument_category',
        'is_permanent', 'is_reusable', 'fda_clearance_year',
        'product_name', 'indicated_for', 'contraindicated_for',
        'elastic_modulus', 'fda_product_code', 'gmdn_code'
    ]

    implant = ImplantNode(name="Test Device")
    for field in required_fields:
        assert hasattr(implant, field), f"Missing field: {field}"

    print("✓ All v7.1 fields present\n")


if __name__ == "__main__":
    print("=" * 60)
    print("ImplantNode Consolidation Test (v7.1)")
    print("=" * 60 + "\n")

    test_implant_device()
    test_instrument_device()
    test_consumable_device()
    test_backward_compatibility()
    test_all_new_fields()

    print("=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
