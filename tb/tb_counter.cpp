// C++ testbench for the counter (the classic Verilator style).
// The C++ code drives the clock itself, so no Verilog delays (#5) are needed.
// That avoids Verilator's "timing" mode, which needs a recent C++20 compiler.
// Prints "TEST PASSED" or "TEST FAILED: <n> errors" for the metrics script.
#include <cstdio>
#include <memory>
#include "Vcounter.h"
#include "verilated.h"

static int errors = 0;

// One full clock cycle: rising edge, then falling edge.
static void tick(Vcounter* dut) {
    dut->clk = 1;
    dut->eval();
    dut->clk = 0;
    dut->eval();
}

static void expect(Vcounter* dut, unsigned expected, const char* what) {
    if (dut->count != expected) {
        std::printf("ERROR (%s): count=%u, expected %u\n", what, dut->count, expected);
        errors++;
    }
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    std::unique_ptr<Vcounter> dut(new Vcounter);
    dut->clk = 0;

    // 1) Reset
    dut->rst = 1;
    dut->en = 0;
    tick(dut.get());
    expect(dut.get(), 0, "after reset");

    // 2) Count 10 cycles with enable high
    dut->rst = 0;
    dut->en = 1;
    for (unsigned i = 1; i <= 10; i++) {
        tick(dut.get());
        expect(dut.get(), i, "counting");
    }

    // 3) Hold the value with enable low
    dut->en = 0;
    for (int i = 0; i < 3; i++) tick(dut.get());
    expect(dut.get(), 10, "while disabled");

    // 4) Wrap-around: 246 more cycles take 10 -> 255 -> 0 (8-bit counter)
    dut->en = 1;
    for (int i = 0; i < 246; i++) tick(dut.get());
    expect(dut.get(), 0, "after wrap-around");

    dut->final();
    if (errors == 0) std::printf("TEST PASSED\n");
    else             std::printf("TEST FAILED: %d errors\n", errors);
    return errors == 0 ? 0 : 1;
}
