export function SoundStatus(props: { enabled: boolean }) {
  return (
    <div className="sound-status">
      {props.enabled ? (
        <span className="eq-bars" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </span>
      ) : (
        <span className="eq-bars eq-bars-off" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </span>
      )}
      <span>{props.enabled ? "Sound on" : "Sound off"}</span>
    </div>
  );
}
