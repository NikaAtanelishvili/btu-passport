"use client";

// Server-paginated table: the page passes one page of rows plus the total; search and
// filter controls sit above it in `toolbar`. Phones get one card per row instead of a table
// that would scroll sideways: `mobileCard` if given, else every column as label and value.
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export type Column<T> = { header: string; cell: (row: T) => React.ReactNode; className?: string };

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  total,
  page,
  pageSize,
  onPageChange,
  onRowClick,
  loading,
  empty,
  toolbar,
  mobileCard,
}: {
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string | number;
  total?: number;
  page?: number;
  pageSize?: number;
  onPageChange?: (page: number) => void;
  onRowClick?: (row: T) => void;
  loading?: boolean;
  empty: React.ReactNode;
  toolbar?: React.ReactNode;
  mobileCard?: (row: T) => React.ReactNode;
}) {
  const pages = total && pageSize ? Math.max(1, Math.ceil(total / pageSize)) : 1;
  return (
    <div className="space-y-3">
      {toolbar && <div className="flex flex-wrap items-end gap-3">{toolbar}</div>}
      <div className="space-y-3 sm:hidden">
        {loading && !rows ? (
          <Skeleton className="h-24 w-full rounded-[24px]" />
        ) : rows && rows.length > 0 ? (
          rows.map((row) => (
            <Card
              key={rowKey(row)}
              className={cn("py-5", onRowClick && "cursor-pointer")}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              <CardContent className="space-y-1.5 px-5 text-base">
                {mobileCard ? (
                  mobileCard(row)
                ) : (
                  <dl className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-3 gap-y-2">
                    {columns.map((c) => (
                      <div key={c.header} className="contents">
                        <dt className="eyebrow pt-1 text-muted-foreground">{c.header}</dt>
                        <dd className="min-w-0 break-words">{c.cell(row)}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </CardContent>
            </Card>
          ))
        ) : (
          <p className="rounded-[24px] border-[1.5px] border-dashed border-foreground px-4 py-8 text-center text-muted-foreground">{empty}</p>
        )}
      </div>
      <div className="hidden sm:block">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((c) => (
                <TableHead key={c.header} className={c.className}>
                  {c.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && !rows ? (
              <TableRow>
                <TableCell colSpan={columns.length}>
                  <Skeleton className="h-6 w-full" />
                </TableCell>
              </TableRow>
            ) : rows && rows.length > 0 ? (
              rows.map((row) => (
                <TableRow
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={onRowClick ? "cursor-pointer" : undefined}
                >
                  {columns.map((c) => (
                    <TableCell key={c.header} className={c.className}>
                      {c.cell(row)}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="py-6 text-center text-muted-foreground">
                  {empty}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      {onPageChange && page && total !== undefined && pages > 1 && (
        <div className="flex flex-wrap items-center justify-end gap-2 text-sm">
          <span className="text-muted-foreground">
            Page {page} of {pages} · {total} total
          </span>
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
            Previous
          </Button>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
