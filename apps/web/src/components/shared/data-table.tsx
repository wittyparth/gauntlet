"use client";

import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { LoadingRows } from "@/components/shared/loading";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export function DataTable<T>({
  columns,
  data,
  getRowId,
  rowHref,
  onRowClick,
  onRowOpen,
  selectedId,
  emptyState,
  isLoading,
  rowTestId,
  rowClassName,
}: {
  columns: ColumnDef<T, unknown>[];
  data: T[];
  getRowId: (row: T) => string;
  /** Rows become links: Enter or click navigates. */
  rowHref?: (row: T) => string;
  onRowClick?: (row: T) => void;
  /** Enter or double click; defaults to onRowClick. */
  onRowOpen?: (row: T) => void;
  selectedId?: string | null;
  emptyState?: ReactNode;
  isLoading?: boolean;
  rowTestId?: string;
  rowClassName?: (row: T) => string | undefined;
}) {
  const router = useRouter();
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getRowId,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (isLoading) return <LoadingRows />;
  if (data.length === 0 && emptyState) return <>{emptyState}</>;

  const interactive = Boolean(rowHref || onRowClick);
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader className="bg-background sticky top-0 z-10">
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id}>
              {hg.headers.map((h) => (
                <TableHead key={h.id} className="h-9 text-xs">
                  {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
            {table.getRowModel().rows.map((row) => {
              const original = row.original;
              const id = row.id;
              const go = () => {
                if (onRowClick) onRowClick(original);
                else if (rowHref) router.push(rowHref(original));
              };
              return (
                <TableRow
                  key={id}
                  data-testid={rowTestId}
                  data-row-id={id}
                  aria-selected={selectedId === id || undefined}
                  tabIndex={interactive ? 0 : undefined}
                  onClick={interactive ? go : undefined}
                  onDoubleClick={onRowOpen ? () => onRowOpen(original) : undefined}
                  onKeyDown={
                    interactive
                      ? (e) => {
                          if (e.key === "Enter") {
                            if (onRowOpen) onRowOpen(original);
                            else go();
                          }
                        }
                      : undefined
                  }
                  className={cn(
                    "h-9",
                    interactive && "cursor-pointer",
                    selectedId === id && "bg-muted",
                    rowClassName?.(original),
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id} className="py-1">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              );
            })}
        </TableBody>
      </Table>
    </div>
  );
}
