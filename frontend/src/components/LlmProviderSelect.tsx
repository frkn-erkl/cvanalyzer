import type { LlmProvider } from "../types";

type Props = {
  value: LlmProvider;
  onChange: (value: LlmProvider) => void;
  disabled?: boolean;
};

export default function LlmProviderSelect({ value, onChange, disabled }: Props) {
  return (
    <label className="llm-provider-select">
      LLM sağlayıcı
      <select
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as LlmProvider)}
        value={value}
      >
        <option value="local">Local LLM</option>
        <option value="cursor">Cursor API</option>
      </select>
    </label>
  );
}
