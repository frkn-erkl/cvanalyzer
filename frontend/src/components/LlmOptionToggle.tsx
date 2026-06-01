type Props = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
};

export default function LlmOptionToggle({ checked, onChange, disabled }: Props) {
  return (
    <label className="checkbox llm-option-toggle" title="Yerel LLM ile zenginleştirilmiş öneri üret">
      <input
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        type="checkbox"
      />
      LLM önerisi iste
    </label>
  );
}
