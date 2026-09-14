import { Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { t } from "@/i18n";

export function OnboardingPage() {
  const { me } = useAuth();
  return (
    <div className="page-pad onboarding-page">
      <h1>{t("onboardingTitle")}</h1>
      <p className="lead">{t("onboardingBody")}</p>
      {me && (
        <p className="muted">
          {t("tenantId")}: <code>{me.tenant_id}</code> · {t("roles")}:{" "}
          {me.roles.join(", ")}
        </p>
      )}
      <ol className="steps">
        <li>
          <Link to="/permissions">{t("permissions")}</Link>
        </li>
        <li>
          <Link to="/map">{t("map")}</Link>
        </li>
        <li>
          <Link to="/alerts">{t("alerts")}</Link>
        </li>
        <li>
          <Link to="/analytics">{t("analytics")}</Link>
        </li>
      </ol>
      <Link className="primary btn-link" to="/map">
        {t("continueToMap")}
      </Link>
    </div>
  );
}
