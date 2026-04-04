---
name: data-viz
description: Use when building charts, graphs, dashboards, data tables, or any visual representation of data. Covers Recharts, Chart.js, D3, Tremor, and dashboard layout patterns.
---

# Data Visualization

## Chart Selection

| Data type | Best chart | Library |
|-----------|-----------|---------|
| Trend over time | Line chart | Recharts, Chart.js |
| Comparison | Bar chart (vertical) | Recharts, Chart.js |
| Ranking | Bar chart (horizontal) | Recharts |
| Part of whole | Donut chart (not pie) | Recharts, Chart.js |
| Distribution | Histogram, box plot | D3, Recharts |
| Correlation | Scatter plot | Recharts, D3 |
| Geographic | Map (choropleth) | D3, Mapbox |
| Flow/Process | Sankey diagram | D3 |
| Hierarchy | Treemap | D3, Recharts |
| Single value | Stat card / KPI | Custom component |
| Progress | Progress bar, gauge | Custom |
| Real-time | Sparkline | Recharts |

### Don't Use
- **Pie charts** — donut is always better (center stat adds context)
- **3D charts** — distort perception, never more readable
- **Dual Y-axis** — confusing, use two separate charts instead
- **Stacked bar (>3 segments)** — becomes unreadable

## Recharts (React — Recommended)

```bash
npm install recharts
```

### Line Chart
```tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"

const data = [
  { date: "Jan", revenue: 4000, users: 2400 },
  { date: "Feb", revenue: 5200, users: 2800 },
  { date: "Mar", revenue: 6800, users: 3200 },
]

<ResponsiveContainer width="100%" height={300}>
  <LineChart data={data}>
    <XAxis dataKey="date" />
    <YAxis />
    <Tooltip />
    <Line type="monotone" dataKey="revenue" stroke="#3b82f6" strokeWidth={2} dot={false} />
    <Line type="monotone" dataKey="users" stroke="#8b5cf6" strokeWidth={2} dot={false} />
  </LineChart>
</ResponsiveContainer>
```

### Bar Chart
```tsx
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"

<ResponsiveContainer width="100%" height={300}>
  <BarChart data={data}>
    <XAxis dataKey="name" />
    <YAxis />
    <Tooltip />
    <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
  </BarChart>
</ResponsiveContainer>
```

### Donut Chart
```tsx
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts"

const COLORS = ["#3b82f6", "#8b5cf6", "#06b6d4", "#f59e0b"]

<ResponsiveContainer width="100%" height={200}>
  <PieChart>
    <Pie data={data} dataKey="value" innerRadius={60} outerRadius={80} paddingAngle={2}>
      {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
    </Pie>
  </PieChart>
</ResponsiveContainer>
```

## Tremor (Dashboard Components)

```bash
npm install @tremor/react
```

```tsx
import { Card, Metric, Text, AreaChart, BarList } from "@tremor/react"

// KPI Card
<Card>
  <Text>Revenue</Text>
  <Metric>$45,231</Metric>
  <Text className="text-green-500">+12.5% from last month</Text>
</Card>

// Area Chart
<Card>
  <AreaChart
    data={chartData}
    index="date"
    categories={["Revenue", "Expenses"]}
    colors={["blue", "red"]}
  />
</Card>

// Bar List (rankings)
<Card>
  <BarList data={[
    { name: "Google", value: 456 },
    { name: "Direct", value: 351 },
    { name: "Twitter", value: 271 },
  ]} />
</Card>
```

## Dashboard Layout

### KPI Row + Charts Grid
```tsx
<div className="space-y-6">
  {/* KPI Row */}
  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
    <StatCard title="Revenue" value="$45,231" change="+12.5%" />
    <StatCard title="Users" value="2,420" change="+8.1%" />
    <StatCard title="Conversion" value="3.2%" change="-0.4%" negative />
    <StatCard title="Churn" value="2.1%" change="-0.3%" />
  </div>

  {/* Charts Grid */}
  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <Card><RevenueChart /></Card>
    <Card><UserGrowthChart /></Card>
  </div>

  {/* Full-width table */}
  <Card><DataTable /></Card>
</div>
```

### Stat Card Component
```tsx
function StatCard({ title, value, change, negative }: {
  title: string; value: string; change: string; negative?: boolean
}) {
  return (
    <div className="rounded-lg border bg-white p-6 dark:bg-gray-900">
      <p className="text-sm text-gray-500">{title}</p>
      <p className="mt-1 text-3xl font-semibold">{value}</p>
      <p className={cn("mt-1 text-sm", negative ? "text-red-500" : "text-green-500")}>
        {change}
      </p>
    </div>
  )
}
```

## Data Table

```tsx
// Using @tanstack/react-table
import { useReactTable, getCoreRowModel, getSortedRowModel,
         getPaginationRowModel, flexRender } from "@tanstack/react-table"

const columns = [
  { accessorKey: "name", header: "Name", cell: info => info.getValue() },
  { accessorKey: "revenue", header: "Revenue",
    cell: info => `$${info.getValue().toLocaleString()}` },
  { accessorKey: "growth", header: "Growth",
    cell: info => <Badge color={info.getValue() > 0 ? "green" : "red"}>
      {info.getValue()}%
    </Badge>
  },
]
```

## Chart Styling Best Practices

### Colors
```
Series 1: #3b82f6 (blue)
Series 2: #8b5cf6 (violet)
Series 3: #06b6d4 (cyan)
Series 4: #f59e0b (amber)
Series 5: #ef4444 (red)
Series 6: #22c55e (green)

Max 6 series per chart. More = use a different visualization.
```

### Typography in Charts
- Axis labels: `text-xs text-gray-500` (12px, muted)
- Axis ticks: `text-xs text-gray-400`
- Chart title: `text-sm font-medium` (14px)
- Tooltips: `text-sm` with clear value formatting
- No chart title if surrounding card has a title

### Formatting Numbers
```typescript
// Abbreviate large numbers
function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}

// Currency
new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(1234.56)
// → "$1,234.56"

// Percentage
new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 1 }).format(0.125)
// → "12.5%"
```

## Real-Time Data

```tsx
// WebSocket + chart update
import { useEffect, useState } from "react"

function LiveChart() {
  const [data, setData] = useState<Point[]>([])

  useEffect(() => {
    const ws = new WebSocket("wss://api.example.com/stream")
    ws.onmessage = (event) => {
      const point = JSON.parse(event.data)
      setData(prev => [...prev.slice(-100), point]) // keep last 100 points
    }
    return () => ws.close()
  }, [])

  return <LineChart data={data} />
}
```

## Visualization Libraries Comparison

| Library | Best for | Learning curve | Size |
|---------|----------|---------------|------|
| **Recharts** | React dashboards, standard charts | Low | 150KB |
| **Tremor** | Business dashboards (pre-built) | Very low | 200KB |
| **Chart.js** | Simple charts, non-React | Low | 60KB |
| **D3** | Custom, complex, interactive | High | 80KB |
| **Visx** | D3 primitives for React | Medium | Modular |
| **Nivo** | Beautiful defaults, React | Low | 150KB |
| **Observable Plot** | Quick exploratory charts | Low | 40KB |

## Data Viz Checklist

- [ ] Chart type matches the data story (trend, comparison, composition)
- [ ] Y-axis starts at 0 for bar charts (not misleading)
- [ ] Max 6 data series per chart
- [ ] Colors are distinguishable (colorblind-safe)
- [ ] Tooltips show exact values on hover
- [ ] Responsive: charts resize with container
- [ ] Large numbers abbreviated (1.2M not 1,200,000)
- [ ] Currency and percentage formatted consistently
- [ ] Empty state when no data ("No data for this period")
- [ ] Loading skeleton while data fetches
- [ ] Dark mode supported (axis colors, grid lines, tooltips)
