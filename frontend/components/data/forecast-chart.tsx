import { dateOnly } from "@/lib/format";
import type { ForecastPoint } from "@/lib/types";

/**
 * Observed admissions and their projection, on one axis.
 *
 * Hand-rolled SVG rather than a charting library: none is installed, and
 * DESIGN.md's motion budget (`MOTION_INTENSITY: 2`) rules out the animated
 * entrances every charting default ships with. What is needed here is a
 * polyline, a shaded interval, and a divider -- roughly forty lines of SVG
 * against a dependency that would arrive with its own visual language.
 *
 * Colour comes only from theme tokens via `currentColor`, so the chart follows
 * `prefers-color-scheme` with no dark-mode variant of its own.
 *
 * The chart is `aria-hidden` and paired with a visually hidden table carrying
 * the same numbers. A screen reader gets the data rather than a description of
 * a picture of the data.
 */

const WIDTH = 720;
const HEIGHT = 180;
const PADDING_Y = 12;

export function ForecastChart({
  history,
  points,
  historyWindowDays,
}: {
  history: number[];
  points: ForecastPoint[];
  historyWindowDays: number;
}) {
  // A tail of history keeps the projection legible; thirty flat days of a
  // quiet ward would squash the part anybody is looking at.
  const observed = history.slice(-14);
  const total = observed.length + points.length;

  if (total < 2) return null;

  const ceiling = Math.max(
    1,
    ...observed,
    ...points.map((point) => point.upper_bound),
  );

  const x = (index: number) => (index / (total - 1)) * WIDTH;
  const y = (value: number) =>
    HEIGHT - PADDING_Y - (value / ceiling) * (HEIGHT - PADDING_Y * 2);

  const observedPath = observed.map((value, index) => `${x(index)},${y(value)}`).join(" ");

  const forecastStartIndex = observed.length - 1;
  const forecastPath = [
    observed.length > 0 ? `${x(forecastStartIndex)},${y(observed[observed.length - 1])}` : "",
    ...points.map((point, index) =>
      `${x(observed.length + index)},${y(point.predicted_admissions)}`,
    ),
  ]
    .filter(Boolean)
    .join(" ");

  const bandTop = points.map((point, index) =>
    `${x(observed.length + index)},${y(point.upper_bound)}`,
  );
  const bandBottom = points
    .map((point, index) => `${x(observed.length + index)},${y(point.lower_bound)}`)
    .reverse();
  const band = [...bandTop, ...bandBottom].join(" ");

  const divider = x(forecastStartIndex);

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-44 w-full text-primary"
        preserveAspectRatio="none"
        aria-hidden="true"
        focusable="false"
      >
        <polygon points={band} className="fill-primary/12" />
        <line
          x1={divider}
          y1={0}
          x2={divider}
          y2={HEIGHT}
          className="stroke-border"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
        <polyline
          points={observedPath}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <polyline
          points={forecastPath}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeDasharray="5 4"
          strokeLinejoin="round"
          strokeLinecap="round"
          opacity={0.75}
        />
      </svg>

      <figcaption className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-xs text-muted-foreground">
        <span>
          Solid: last {observed.length} days of {historyWindowDays} observed
        </span>
        <span>Dashed: projection</span>
        <span>Shaded: 95% interval</span>
      </figcaption>

      <table className="sr-only">
        <caption>Projected daily admissions with a 95% confidence interval</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Projected admissions</th>
            <th scope="col">Lower bound</th>
            <th scope="col">Upper bound</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.horizon_day}>
              <th scope="row">{dateOnly(point.forecast_date)}</th>
              <td>{point.predicted_admissions.toFixed(1)}</td>
              <td>{point.lower_bound.toFixed(1)}</td>
              <td>{point.upper_bound.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
