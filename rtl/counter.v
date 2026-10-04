// 8-bit up-counter with synchronous reset and enable.
// Small on purpose: the point of this repo is the flow and the metrics pipeline.
module counter #(
    parameter WIDTH = 8
) (
    input  wire             clk,
    input  wire             rst,     // synchronous, active high
    input  wire             en,      // count only when high
    output reg  [WIDTH-1:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= {WIDTH{1'b0}};
        else if (en)
            count <= count + 1'b1;
    end
endmodule
