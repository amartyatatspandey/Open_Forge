"""Fixed benchmark task set for the OpenForge search controller.

15 tasks across three difficulty levels:
  Simple  (5): single topology, 1-3 components
  Medium  (5): compound design, 3-6 components, 2 topologies
  Hard    (5): multi-topology or precision/specialty circuits from
               the scientist prompt analysis log

These tasks are FIXED — do not add, remove, or modify tasks between
benchmark runs. Changes invalidate historical comparisons.
"""

from __future__ import annotations
from eval.benchmarks.task_schema import BenchmarkTask

BENCHMARK_TASKS: list[BenchmarkTask] = [

    # ── SIMPLE ────────────────────────────────────────────────────────────────

    BenchmarkTask(
        task_id="TASK_001",
        prompt="Design a 3.3V LDO linear voltage regulator for an IoT sensor board",
        difficulty="simple",
        expected_component_types=["ldo_regulator"],
        expected_topologies=["ldo"],
        min_erc_score=0.90,
        source="canonical",
        notes="Baseline single-component design. Should be trivially solvable.",
    ),

    BenchmarkTask(
        task_id="TASK_002",
        prompt="Design an inverting op-amp amplifier with gain of -10",
        difficulty="simple",
        expected_component_types=["op_amp", "resistor"],
        expected_topologies=["inverting_amplifier"],
        min_erc_score=0.90,
        source="canonical",
    ),

    BenchmarkTask(
        task_id="TASK_003",
        prompt="Design an RC low-pass filter with cutoff frequency of 1kHz",
        difficulty="simple",
        expected_component_types=["resistor", "capacitor"],
        expected_topologies=["rc_lowpass"],
        min_erc_score=0.90,
        source="canonical",
    ),

    BenchmarkTask(
        task_id="TASK_004",
        prompt="Design a voltage divider to step down 5V to 3.3V using resistors",
        difficulty="simple",
        expected_component_types=["resistor"],
        expected_topologies=["voltage_divider"],
        min_erc_score=0.90,
        source="canonical",
    ),

    BenchmarkTask(
        task_id="TASK_005",
        prompt="Design the decoupling capacitor network for a 3.3V microcontroller power supply",
        difficulty="simple",
        expected_component_types=["capacitor"],
        expected_topologies=[],
        min_erc_score=0.85,
        source="canonical",
        notes="Topology check skipped — decoupling has no standard topology template.",
    ),

    # ── MEDIUM ────────────────────────────────────────────────────────────────

    BenchmarkTask(
        task_id="TASK_006",
        prompt=(
            "Design a 5V to 3.3V LDO power supply with an op-amp unity-gain buffer "
            "on the output for driving a capacitive load"
        ),
        difficulty="medium",
        expected_component_types=["ldo_regulator", "op_amp"],
        expected_topologies=["ldo"],
        min_erc_score=0.85,
        source="canonical",
    ),

    BenchmarkTask(
        task_id="TASK_007",
        prompt=(
            "Design the power supply section for an STM32 microcontroller: "
            "3.3V LDO, decoupling capacitors, and a 16MHz crystal oscillator"
        ),
        difficulty="medium",
        expected_component_types=["ldo_regulator", "capacitor", "crystal"],
        expected_topologies=["ldo"],
        min_erc_score=0.85,
        source="canonical",
    ),

    BenchmarkTask(
        task_id="TASK_008",
        prompt=(
            "Design an SPI bus connecting a microcontroller to an ADC and a DAC "
            "with appropriate pull-up resistors on CS lines"
        ),
        difficulty="medium",
        expected_component_types=["adc", "dac", "resistor"],
        expected_topologies=[],
        min_erc_score=0.80,
        source="canonical",
    ),

    BenchmarkTask(
        task_id="TASK_009",
        prompt=(
            "Design a precision current sensor using an INA219 with a 0.1 ohm "
            "shunt resistor on a 5V bus, I2C interface"
        ),
        difficulty="medium",
        expected_component_types=["adc", "resistor"],
        expected_topologies=[],
        min_erc_score=0.85,
        source="corpus",
        notes="INA219 is in the golden corpus — TI_INA219_v1.",
    ),

    BenchmarkTask(
        task_id="TASK_010",
        prompt=(
            "Design a synchronous buck converter stepping down 12V to 5V at 2A "
            "with an external inductor and output capacitors"
        ),
        difficulty="medium",
        expected_component_types=["buck_converter", "inductor", "capacitor"],
        expected_topologies=["buck_converter"],
        min_erc_score=0.85,
        source="canonical",
    ),

    # ── HARD ──────────────────────────────────────────────────────────────────

    BenchmarkTask(
        task_id="TASK_011",
        prompt=(
            "Design a precision current source capable of 100mA with sub-ppm "
            "stability using zero-drift op-amps and ultra-precision resistors, "
            "following the Libbrecht-Hall topology"
        ),
        difficulty="hard",
        expected_component_types=["op_amp", "resistor"],
        expected_topologies=["current_source"],
        min_erc_score=0.80,
        source="scientist_log",
        notes=(
            "GAP-001-A from SCIENTIFIC_PROMPT_ANALYSIS_LOG. This is the hardest "
            "task in the set. Requires Libbrecht-Hall topology knowledge in KG-2."
        ),
    ),

    BenchmarkTask(
        task_id="TASK_012",
        prompt=(
            "Design a VCO bias tee circuit for a ZCOM ZOS-2600+ VCO: "
            "DC bias injection with RF signal isolation, 50 ohm impedance"
        ),
        difficulty="hard",
        expected_component_types=["inductor", "capacitor"],
        expected_topologies=[],
        min_erc_score=0.80,
        source="scientist_log",
        notes="GAP-002-C from SCIENTIFIC_PROMPT_ANALYSIS_LOG. RF topology.",
    ),

    BenchmarkTask(
        task_id="TASK_013",
        prompt=(
            "Design a precision analog measurement chain: LDO power supply, "
            "zero-drift instrumentation amplifier, 16-bit SAR ADC with a "
            "precision voltage reference"
        ),
        difficulty="hard",
        expected_component_types=["ldo_regulator", "op_amp", "adc"],
        expected_topologies=["ldo"],
        min_erc_score=0.80,
        source="scientist_log",
        notes="Multi-topology compound design combining GAP-001 and GAP-002 demands.",
    ),

    BenchmarkTask(
        task_id="TASK_014",
        prompt=(
            "Design a USB-to-UART bridge circuit with automatic baud rate detection, "
            "3.3V level shifters, and ESD protection on USB lines"
        ),
        difficulty="hard",
        expected_component_types=["capacitor", "resistor"],
        expected_topologies=[],
        min_erc_score=0.80,
        source="scientist_log",
        notes="GAP-002-D from SCIENTIFIC_PROMPT_ANALYSIS_LOG.",
    ),

    BenchmarkTask(
        task_id="TASK_015",
        prompt=(
            "Design a 5W synchronous buck converter with closed-loop feedback: "
            "input filter, buck stage, output LC filter, feedback voltage divider, "
            "and soft-start capacitor"
        ),
        difficulty="hard",
        expected_component_types=["buck_converter", "inductor", "capacitor", "resistor"],
        expected_topologies=["buck_converter", "voltage_divider", "rc_lowpass"],
        min_erc_score=0.80,
        source="canonical",
        notes="Multi-topology: buck + voltage divider feedback + LC output filter.",
    ),
]

# Index for fast lookup
TASKS_BY_ID: dict[str, BenchmarkTask] = {t.task_id: t for t in BENCHMARK_TASKS}

__all__ = ["BENCHMARK_TASKS", "TASKS_BY_ID"]
