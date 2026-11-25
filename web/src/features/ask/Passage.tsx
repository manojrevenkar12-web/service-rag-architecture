import "./passage.css";

/** A cited passage shown the way the manual prints it, with the line the answer came from marked. */
export function Passage({ text, line }: { text: string; line: string | null }) {
  const [crumb, ...lines] = text.split("\n");
  const table = lines.filter((l) => l.includes(" | "));
  const header = table[0]?.split(" | ");
  return (
    <figure className="passage">
      <figcaption>{crumb.replace(/^\[|\]$/g, "")}</figcaption>
      {header && table.length > 1 ? (
        <div className="passage-scroll">
          <table>
            <thead><tr>{header.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
            <tbody>
              {table.slice(1).map((row) => {
                const cells = row.split(" | ");
                const hit = line !== null && row === line;
                return <tr key={row} className={hit ? "hit" : ""}>{cells.map((c, i) => <td key={i}>{c}</td>)}</tr>;
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="passage-lines">
          {lines.map((l) => <p key={l} className={l === line ? "hit" : ""}>{l}</p>)}
        </div>
      )}
    </figure>
  );
}
