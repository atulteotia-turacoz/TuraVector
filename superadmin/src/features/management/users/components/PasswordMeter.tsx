/** Password strength indicators from create_user.html and change_user_password.html (same scoring rules). */

export function createStrength(password: string) {
  let strength = 0;
  if (password.length >= 8) strength += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength += 1;
  if (/[0-9]/.test(password)) strength += 1;
  if (/[^a-zA-Z0-9]/.test(password)) strength += 1;
  const text = strength <= 1 ? 'Very Weak' : strength === 2 ? 'Weak' : strength === 3 ? 'Good' : 'Strong';
  const tone = strength <= 1 ? 'over' : strength === 2 ? 'warn' : '';
  return { percentage: (strength / 4) * 100, text, tone };
}

export function changeStrength(password: string) {
  let strength = 0;
  if (password.length >= 8) strength += 20;
  if (/[a-z]/.test(password)) strength += 20;
  if (/[A-Z]/.test(password)) strength += 20;
  if (/[0-9]/.test(password)) strength += 20;
  if (/[^a-zA-Z0-9]/.test(password)) strength += 20;
  let text = 'Very Weak';
  let tone = 'over';
  if (strength >= 80) { text = 'Very Strong'; tone = ''; }
  else if (strength >= 60) { text = 'Strong'; tone = ''; }
  else if (strength >= 40) { text = 'Fair'; tone = 'warn'; }
  else if (strength >= 20) { text = 'Weak'; tone = 'warn'; }
  return { percentage: strength, text, tone };
}

export function PasswordMeter({ password, variant }: { password: string; variant: 'create' | 'change' }) {
  const s = variant === 'create' ? createStrength(password) : changeStrength(password);
  const label = variant === 'create'
    ? (password ? s.text : 'Password strength will be shown here')
    : (password ? s.text : 'Enter password');
  return (
    <div>
      <div className="meter"><div className={`meter-fill ${s.tone}`} style={{ width: `${password ? s.percentage : 0}%` }} /></div>
      <span className="field-help">{variant === 'change' && 'Password Strength: '}{label}</span>
    </div>
  );
}
