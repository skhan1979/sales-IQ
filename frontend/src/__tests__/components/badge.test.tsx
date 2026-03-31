import React from "react";
import { render, screen } from "@testing-library/react";
import { Badge } from "@/components/ui/badge";

describe("Badge", () => {
  it("renders children text", () => {
    render(<Badge>Active</Badge>);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("applies success variant (emerald)", () => {
    render(<Badge variant="success">OK</Badge>);
    expect(screen.getByText("OK").className).toContain("emerald");
  });

  it("applies danger variant (red)", () => {
    render(<Badge variant="danger">Error</Badge>);
    expect(screen.getByText("Error").className).toContain("red");
  });

  it("applies warning variant (amber)", () => {
    render(<Badge variant="warning">Warn</Badge>);
    expect(screen.getByText("Warn").className).toContain("amber");
  });

  it("applies info variant (blue)", () => {
    render(<Badge variant="info">Info</Badge>);
    expect(screen.getByText("Info").className).toContain("blue");
  });

  it("shows dot indicator when dot prop is true", () => {
    const { container } = render(<Badge dot variant="success">Status</Badge>);
    const spans = container.querySelectorAll("span");
    // Outer badge + inner dot + text = at least 2 spans
    const dotSpan = Array.from(spans).find((s) => s.className.includes("rounded-full") && s.className.includes("h-1.5"));
    expect(dotSpan).toBeTruthy();
  });

  it("does not show dot when dot prop is false", () => {
    const { container } = render(<Badge>No Dot</Badge>);
    const spans = container.querySelectorAll("span");
    const dotSpan = Array.from(spans).find((s) => s.className.includes("h-1.5"));
    expect(dotSpan).toBeFalsy();
  });
});
