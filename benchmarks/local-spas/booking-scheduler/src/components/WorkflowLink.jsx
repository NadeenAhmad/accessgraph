export function WorkflowLink({
  to,
  activationTargetRoute = to,
  onNavigate,
  children,
  ...linkProps
}) {
  function handleClick(event) {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }

    event.preventDefault();
    onNavigate(activationTargetRoute);
  }

  return (
    <a {...linkProps} href={to} onClick={handleClick}>
      {children}
    </a>
  );
}
