import React from "react";
import { render, screen } from "@testing-library/react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { Spinner, PageLoader, InlineLoader } from "@/components/ui/spinner";
import { AlertTriangle } from "lucide-react";

describe("Card", () => {
  it("renders with children", () => {
    render(
      <Card>
        <CardContent>Hello</CardContent>
      </Card>
    );
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("renders header with title", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>My Title</CardTitle>
        </CardHeader>
      </Card>
    );
    expect(screen.getByText("My Title")).toBeInTheDocument();
  });
});

describe("Input", () => {
  it("renders with label", () => {
    render(<Input label="Email" placeholder="Type here" />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("shows error message", () => {
    render(<Input label="Name" error="Required" />);
    expect(screen.getByText("Required")).toBeInTheDocument();
  });

  it("renders icon", () => {
    render(<Input icon={<span data-testid="search-icon">S</span>} />);
    expect(screen.getByTestId("search-icon")).toBeInTheDocument();
  });
});

describe("Select", () => {
  it("renders options", () => {
    render(
      <Select
        label="Country"
        options={[
          { value: "AE", label: "UAE" },
          { value: "SA", label: "KSA" },
        ]}
      />
    );
    expect(screen.getByLabelText("Country")).toBeInTheDocument();
    expect(screen.getByText("UAE")).toBeInTheDocument();
    expect(screen.getByText("KSA")).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("renders title and description", () => {
    render(
      <EmptyState
        icon={AlertTriangle}
        title="No data"
        description="Nothing here yet"
      />
    );
    expect(screen.getByText("No data")).toBeInTheDocument();
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
  });

  it("renders action button", () => {
    render(
      <EmptyState
        title="Empty"
        action={<button>Add new</button>}
      />
    );
    expect(screen.getByText("Add new")).toBeInTheDocument();
  });
});

describe("Spinner components", () => {
  it("renders Spinner", () => {
    const { container } = render(<Spinner />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("renders PageLoader with text", () => {
    render(<PageLoader />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders InlineLoader with custom text", () => {
    render(<InlineLoader text="Fetching data..." />);
    expect(screen.getByText("Fetching data...")).toBeInTheDocument();
  });
});
