export function DashboardMetaForm({
  name,
  description,
  onChangeName,
  onChangeDescription,
}: {
  name: string;
  description: string;
  onChangeName: (v: string) => void;
  onChangeDescription: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <label className="text-xs font-bold text-ink-muted uppercase">Dashboard</label>
      <input
        className="border border-border rounded-lg px-3 py-2 text-sm"
        value={name}
        onChange={(e) => onChangeName(e.target.value)}
        placeholder="Nombre"
      />
      <textarea
        className="border border-border rounded-lg px-3 py-2 text-sm"
        value={description}
        onChange={(e) => onChangeDescription(e.target.value)}
        placeholder="Descripción"
      />
    </div>
  );
}
