import { useEffect, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

interface VirtualizedListProps<T> {
  items: T[];
  rowHeight: number;
  height: number;
  renderRow: (item: T, index: number) => React.ReactNode;
  /** Called when the user scrolls near the end of the currently-loaded rows — load the next chunk here. */
  onEndReached?: () => void;
  /** How many rows from the end triggers onEndReached. */
  endReachedThreshold?: number;
  loadingMore?: boolean;
  emptyState?: React.ReactNode;
}

/**
 * Windowed/virtualized scroll container — only the rows actually in view are
 * mounted, so a "Show all" list backed by tens of thousands of rows stays as
 * responsive as a 50-row page. Pair with chunked fetching via onEndReached
 * (never fetch everything in one request — see investor/batch "show all"
 * modes) so neither the network payload nor the DOM scales with total count.
 */
export function VirtualizedList<T>({
  items,
  rowHeight,
  height,
  renderRow,
  onEndReached,
  endReachedThreshold = 30,
  loadingMore,
  emptyState,
}: VirtualizedListProps<T>) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 12,
  });

  const virtualItems = virtualizer.getVirtualItems();
  const lastItem = virtualItems[virtualItems.length - 1];
  const lastIndex = lastItem ? lastItem.index : -1;

  useEffect(() => {
    if (!onEndReached || items.length === 0) return;
    if (lastIndex >= items.length - endReachedThreshold) {
      onEndReached();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastIndex, items.length]);

  if (items.length === 0 && emptyState) {
    return <>{emptyState}</>;
  }

  return (
    <div ref={parentRef} style={{ height, overflow: "auto" }}>
      <div style={{ height: virtualizer.getTotalSize(), width: "100%", position: "relative" }}>
        {virtualItems.map((vi) => {
          const item = items[vi.index];
          if (item === undefined) return null;
          return (
            <div
              key={vi.key}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                height: `${vi.size}px`,
                transform: `translateY(${vi.start}px)`,
              }}
            >
              {renderRow(item, vi.index)}
            </div>
          );
        })}
      </div>
      {loadingMore && (
        <div style={{ textAlign: "center", padding: "12px", fontSize: "11px", color: "var(--color-text-tertiary)" }}>
          Loading more…
        </div>
      )}
    </div>
  );
}
