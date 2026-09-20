'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Eye, EyeOff, LockKeyhole, MapPinned } from 'lucide-react';
import { API_URL, api } from '../../lib/api';
import { saveUser } from '../../lib/auth';
import { Button, ErrorMessage } from '../../components/common/UI';
import './login.css';

export default function Login() {
  const [role, setRole] = useState('user');
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const router = useRouter();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ticket = params.get('oauth_ticket');
    const googleError = params.get('google_error');
    if (googleError) {
      const messages = {
        cancelled: 'Google sign-in was cancelled. Please try again.',
        submitter_only: 'Google sign-in is available only for Record Submitters.',
        account_mismatch: 'This Google account is linked to a different BhumiAI account.',
      };
      setError(messages[googleError] || 'Google sign-in could not be completed. Please try again.');
      return;
    }
    if (!ticket) return;
    setLoading(true);
    api.googleExchange(ticket)
      .then(({ user }) => {
        saveUser(user);
        router.replace('/user');
      })
      .catch((exchangeError) => setError(exchangeError.message))
      .finally(() => setLoading(false));
  }, [router]);

  function changeRole(event) {
    setRole(event.target.value);
    setMode('login');
    setError('');
    setSuccess('');
    setShowPassword(false);
  }

  function switchMode(nextMode) {
    setMode(nextMode);
    setError('');
    setSuccess('');
    setShowPassword(false);
  }

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');
    const form = new FormData(event.currentTarget);
    try {
      if (role === 'user' && mode === 'register') {
        const password = form.get('password');
        if (password !== form.get('confirm_password')) throw new Error('Passwords do not match.');
        await api.register({ name: form.get('name').trim(), email: form.get('email').trim(), password });
        setEmail(form.get('email').trim());
        setMode('login');
        setSuccess('Account created successfully. Please sign in.');
        return;
      }
      const result = await api.login({
        email: form.get('email'),
        officer_id: form.get('officer_id'),
        password: form.get('password'),
        role,
      });
      if (result.user.role !== role) throw new Error('This credential is not assigned to the selected workspace.');
      saveUser(result.user);
      router.push(role === 'officer' ? '/officer' : '/user');
    } catch (loginError) {
      setError(loginError.message);
    } finally {
      setLoading(false);
    }
  }

  function signInWithGoogle() {
    setLoading(true);
    window.location.assign(`${API_URL}/api/auth/google/start`);
  }

  return <main className="login-page cadastral-login">
    <div className="cadastral-environment" aria-hidden="true">
      <svg className="cadastral-map" viewBox="0 0 1600 1000" fill="none" preserveAspectRatio="xMidYMid slice" focusable="false">
        {/* Abstract geometry only; these guides do not describe actual land records. */}
        <g className="map-parcels">
          <path d="M-80 305 170 270 315 320 485 235 665 280 800 210 1010 255 1170 185 1430 245 1680 200M-40 510 155 440 340 485 485 405 660 450 820 390 1030 445 1210 345 1450 390 1660 340M-60 740 160 650 345 705 525 610 725 680 900 600 1095 665 1240 565 1455 620 1650 545M-30 940 200 865 380 920 550 805 785 860 970 780 1165 840 1360 775 1640 820" />
          <path d="M170 270 155 440 160 650 200 865M315 320 340 485 345 705 380 920M485 235 485 405 525 610 550 805M665 280 660 450 725 680 785 860M800 210 820 390 900 600 970 780M1010 255 1030 445 1095 665 1165 840M1170 185 1210 345 1240 565 1360 775M1430 245 1450 390 1455 620" />
          <path d="M160 650 260 598 345 620M485 405 575 358 665 380M1095 665 1188 725 1297 666M1210 345 1325 292 1440 319M200 865 178 975M1360 775 1390 1020M800 210 760 -30M1170 185 1140 -20M1430 245 1460 -20" />
        </g>
        <g className="map-insets"><path d="m185 468 129 31 3 97-126 45zM1235 368l188 42 3 184-163-50zM393 733l120-62 19 119-126 84z" /><path d="m1263 386 135 30 4 143-115-35z" /></g>
        <path className="map-gold-parcel" d="m160 650 185 55 35 215-180-55z" />
        <path className="map-gold-edge" d="m1095 665 145-100 215 55" />
        <g className="map-guides" strokeDasharray="3 9"><path d="M0 560H1600M895 0V1000M0 150H1600M295 0V1000" /><circle cx="895" cy="560" r="310" /><circle cx="895" cy="560" r="385" /></g>
        <g className="map-nodes"><circle cx="160" cy="650" r="5" /><circle cx="345" cy="705" r="4" /><circle cx="485" cy="405" r="4" /><circle cx="1095" cy="665" r="5" /><circle cx="1240" cy="565" r="4" /><circle cx="1430" cy="245" r="4" /><path d="M283 560h24m-12-12v24M1228 150h24m-12-12v24M1443 620h24m-12-12v24" /></g>
        <g className="map-labels"><text x="213" y="767">PARCEL</text><text x="1265" y="481">SURVEY</text><text x="395" y="560">RECORD</text><text x="1148" y="884">VERIFIED</text><text x="315" y="175">GRID / A—01</text><text x="1300" y="145">REF / B—02</text></g>
      </svg>
      <div className="survey-compass"><span>N</span><svg viewBox="0 0 40 56" fill="none" focusable="false"><path d="M20 2 32 42 20 34 8 42Z" /><path d="M20 2v50M2 34h36" /></svg></div>
      <div className="map-scale"><span /><small>CADASTRAL / SCHEMATIC</small></div>
    </div>
    <header className="login-branding">
        <div className="logo-line"><span className="logo-mark"><MapPinned size={22} /></span><b>Bhumi<span>AI</span></b></div>
        <p className="initiative-line">An initiative toward smarter, more reliable digitization of land records.</p>
        <p className="team-attribution">Team Pivot</p>
    </header>
    <section className="login-form-wrap" aria-labelledby="login-heading"><form className="login-card" onSubmit={submit}>
      <div className="login-card-heading">
        <div className="eyebrow"><LockKeyhole size={13} /> SECURE ACCESS</div>
        <h1 id="login-heading">{role === 'user' && mode === 'register' ? 'Register as Record Submitter' : role === 'user' ? 'Welcome to BhumiAI' : 'Government Officer Access'}</h1><p>{role === 'user' ? 'Use your email and password, or continue securely with Google.' : 'Use credentials issued by the authorized government administrator.'}</p>
      </div>
      <div className="login-field"><label htmlFor="login-workspace">Workspace</label><select id="login-workspace" value={role} onChange={changeRole}><option value="user">Record Submitter</option><option value="officer">Verification Officer</option></select></div>
      {role === 'user' ? <>
        {mode === 'register' && <div className="login-field"><label htmlFor="login-name">Full Name</label><input id="login-name" name="name" autoComplete="name" placeholder="Your full name" maxLength={120} required /></div>}
        <div className="login-field"><label htmlFor="login-email">Email</label><input id="login-email" name="email" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="user@example.com" required /></div>
        <div className="login-field"><label htmlFor="login-password">Password</label><div className="password-field"><input key={`password-${mode}`} id="login-password" name="password" type={showPassword ? 'text' : 'password'} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} placeholder="Your password" minLength={mode === 'register' ? 8 : undefined} maxLength={128} required /><button type="button" className="password-toggle" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></div>
        {mode === 'register' && <div className="login-field"><label htmlFor="login-confirm-password">Confirm Password</label><input id="login-confirm-password" name="confirm_password" type={showPassword ? 'text' : 'password'} autoComplete="new-password" placeholder="Re-enter your password" minLength={8} maxLength={128} required /></div>}
        <Button loading={loading}>{mode === 'register' ? 'Create Account' : 'Enter Workspace'} <ArrowRight size={17} aria-hidden="true" /></Button>
        <div className="google-divider"><span>or</span></div><button className="google-auth-button" type="button" onClick={signInWithGoogle} disabled={loading}><span className="google-g" aria-hidden="true">G</span>{loading ? 'Opening Google…' : 'Continue with Google'}<ArrowRight size={17} aria-hidden="true" /></button>
        {mode === 'register' ? <p className="auth-context">Already have an account? <button type="button" onClick={() => switchMode('login')}>Sign in</button></p> : <p className="auth-context">New to BhumiAI? <button type="button" onClick={() => switchMode('register')}>Register here</button></p>}
      </> : <>
        <div className="login-field"><label htmlFor="officer-id">Government Officer ID</label><input id="officer-id" name="officer_id" autoComplete="username" placeholder="e.g. GOV-DEV-001" minLength={5} maxLength={64} required /></div>
        <div className="login-field"><label htmlFor="login-password">Issued Password</label><div className="password-field"><input id="login-password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" placeholder="Your issued password" minLength={8} maxLength={128} required /><button type="button" className="password-toggle" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></div>
        <Button loading={loading}>Enter Officer Workspace <ArrowRight size={17} aria-hidden="true" /></Button>
        <p className="auth-context">Officer access is issued by the authorized government administrator. Self-registration is not available.</p>
      </>}
      {success && <div className="login-success" role="status">{success}</div>}
      <ErrorMessage>{error}</ErrorMessage>
    </form><p className="login-system-label"><span aria-hidden="true" /> LAND RECORD INTELLIGENCE</p></section>
  </main>;
}
