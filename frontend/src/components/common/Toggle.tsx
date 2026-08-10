import { useTranslation } from 'react-i18next';

/** 暂停开关（on=已暂停）。workflow 列表页与详情页共用。 */
export const Toggle = ({
  on,
  disabled,
  onChange,
}: {
  on: boolean;
  disabled?: boolean;
  onChange: () => void;
}) => {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={!on}
      disabled={disabled}
      title={on ? t('workflow.toggle.paused') : t('workflow.toggle.running')}
      onClick={(e) => {
        e.stopPropagation();
        onChange();
      }}
      style={{
        width: 38,
        height: 20,
        borderRadius: 999,
        border: '1px solid var(--border-subtle)',
        background: on ? 'var(--bg-surface-2)' : 'var(--positive)',
        position: 'relative',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
        transition: 'background 0.15s',
        padding: 0,
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 1,
          left: on ? 1 : 19,
          width: 16,
          height: 16,
          borderRadius: '50%',
          background: '#fff',
          transition: 'left 0.15s',
        }}
      />
    </button>
  );
};
