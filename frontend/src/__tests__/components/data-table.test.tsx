import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataTable, Column } from "@/components/ui/data-table";

interface TestRow {
  id: string;
  name: string;
  amount: number;
  status: string;
  [key: string]: unknown;
}

const columns: Column<TestRow>[] = [
  { key: "name", header: "Name" },
  { key: "amount", header: "Amount", align: "right", sortable: true },
  {
    key: "status",
    header: "Status",
    render: (val: unknown) => <span data-testid={`status-${val}`}>{val as string}</span>,
  },
];

const data: TestRow[] = [
  { id: "1", name: "Customer A", amount: 1000, status: "active" },
  { id: "2", name: "Customer B", amount: 2000, status: "inactive" },
  { id: "3", name: "Customer C", amount: 500, status: "pending" },
];

describe("DataTable", () => {
  it("renders column headers", () => {
    render(<DataTable columns={columns} data={data} />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Amount")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("renders data rows", () => {
    render(<DataTable columns={columns} data={data} />);
    expect(screen.getByText("Customer A")).toBeInTheDocument();
    expect(screen.getByText("Customer B")).toBeInTheDocument();
    expect(screen.getByText("Customer C")).toBeInTheDocument();
  });

  it("renders custom cell renderers", () => {
    render(<DataTable columns={columns} data={data} />);
    expect(screen.getByTestId("status-active")).toHaveTextContent("active");
    expect(screen.getByTestId("status-inactive")).toHaveTextContent("inactive");
  });

  it("shows loading skeleton", () => {
    const { container } = render(<DataTable columns={columns} data={[]} loading />);
    const pulseElements = container.querySelectorAll(".animate-pulse");
    expect(pulseElements.length).toBeGreaterThan(0);
  });

  it("shows empty message when no data", () => {
    render(<DataTable columns={columns} data={[]} emptyMessage="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });

  it("renders pagination when provided", () => {
    render(
      <DataTable
        columns={columns}
        data={data}
        pagination={{
          page: 1,
          pageSize: 2,
          total: 10,
          onPageChange: jest.fn(),
        }}
      />
    );
    expect(screen.getByText(/Showing 1–2 of 10/)).toBeInTheDocument();
    expect(screen.getByText("1 / 5")).toBeInTheDocument();
  });

  it("calls onRowClick when a row is clicked", async () => {
    const onClick = jest.fn();
    render(<DataTable columns={columns} data={data} onRowClick={onClick} />);
    await userEvent.click(screen.getByText("Customer A"));
    expect(onClick).toHaveBeenCalledWith(data[0]);
  });

  it("shows export button when exportFilename is set", () => {
    render(<DataTable columns={columns} data={data} exportFilename="test" />);
    expect(screen.getByText("Export")).toBeInTheDocument();
  });
});
