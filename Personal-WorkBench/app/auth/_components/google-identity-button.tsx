"use client";

type GoogleIdentityButtonProps = {
  disabled: boolean;
  fallbackHref: string;
  onFallback(): void;
};

/**
 * Google Web OAuth uses the server-owned authorization redirect. This keeps
 * the registered callback and the token exchange on the same audited path,
 * while leaving a real anchor available before client hydration completes.
 */
export function GoogleIdentityButton({
  disabled,
  fallbackHref,
  onFallback,
}: GoogleIdentityButtonProps) {
  function handleClick(event: React.MouseEvent<HTMLAnchorElement>): void {
    if (disabled) {
      event.preventDefault();
      return;
    }
    onFallback();
  }

  return (
    <a
      className="auth-google"
      href={fallbackHref}
      onClick={handleClick}
      aria-disabled={disabled || undefined}
    >
      使用 Google 继续
    </a>
  );
}
