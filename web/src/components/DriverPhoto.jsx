import { useEffect, useState } from "react";
import { getDriverProfile, getTeamStyle } from "../lib/drivers";

export default function DriverPhoto({ code, team, className = "", eager = false }) {
  const profile = getDriverProfile(code);
  const style = getTeamStyle(team, code);
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [profile.portraitUrl]);

  const classNames = ["driver-photo", className].filter(Boolean).join(" ");
  if (!profile.portraitUrl || failed) {
    return (
      <span className={`${classNames} driver-photo--fallback`} style={{ "--team": style.accent }} aria-label={`${profile.name} portrait unavailable`}>
        {(profile.surname || profile.name || code || "?").slice(0, 2).toUpperCase()}
      </span>
    );
  }

  return (
    <img
      className={classNames}
      src={profile.portraitUrl}
      alt={`${profile.name}, ${style.name} driver`}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}
