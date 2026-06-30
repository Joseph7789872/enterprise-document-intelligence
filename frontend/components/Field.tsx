import { forwardRef, useId } from "react";
import { cn } from "./cn";

interface FieldShellProps {
  label?: string;
  required?: boolean;
  helper?: string;
  error?: string;
  className?: string;
  children: (controlProps: {
    id: string;
    className: string;
    "aria-invalid"?: true;
    "aria-describedby"?: string;
  }) => React.ReactNode;
}

/** Shared label + helper/error wrapper used by Input/Textarea/Select. */
function FieldShell({
  label,
  required,
  helper,
  error,
  className,
  children,
}: FieldShellProps) {
  const id = useId();
  const describedBy = error
    ? `${id}-error`
    : helper
      ? `${id}-helper`
      : undefined;
  return (
    <div className={cn("ui-field", error && "ui-field--invalid", className)}>
      {label && (
        <label className="ui-field__label" htmlFor={id}>
          {label}
          {required && (
            <span className="ui-field__required" aria-hidden>
              *
            </span>
          )}
        </label>
      )}
      {children({
        id,
        className: "ui-field__control",
        "aria-invalid": error ? true : undefined,
        "aria-describedby": describedBy,
      })}
      {error ? (
        <p className="ui-field__error" id={`${id}-error`} role="alert">
          {error}
        </p>
      ) : helper ? (
        <p className="ui-field__helper" id={`${id}-helper`}>
          {helper}
        </p>
      ) : null}
    </div>
  );
}

type FieldExtras = {
  label?: string;
  required?: boolean;
  helper?: string;
  error?: string;
  wrapperClassName?: string;
};

export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "className">,
    FieldExtras {}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, required, helper, error, wrapperClassName, ...rest },
  ref,
) {
  return (
    <FieldShell
      label={label}
      required={required}
      helper={helper}
      error={error}
      className={wrapperClassName}
    >
      {(p) => <input ref={ref} required={required} {...p} {...rest} />}
    </FieldShell>
  );
});

export interface TextareaProps
  extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, "className">,
    FieldExtras {}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea(
    { label, required, helper, error, wrapperClassName, ...rest },
    ref,
  ) {
    return (
      <FieldShell
        label={label}
        required={required}
        helper={helper}
        error={error}
        className={wrapperClassName}
      >
        {(p) => <textarea ref={ref} required={required} {...p} {...rest} />}
      </FieldShell>
    );
  },
);

export interface SelectProps
  extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "className">,
    FieldExtras {}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, required, helper, error, wrapperClassName, children, ...rest },
  ref,
) {
  return (
    <FieldShell
      label={label}
      required={required}
      helper={helper}
      error={error}
      className={wrapperClassName}
    >
      {(p) => (
        <select ref={ref} required={required} {...p} {...rest}>
          {children}
        </select>
      )}
    </FieldShell>
  );
});
