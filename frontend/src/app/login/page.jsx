'use client';

import {useState} from 'react';
import {useRouter} from 'next/navigation';
import {ArrowRight, CheckCircle2, FileText, LockKeyhole, MapPinned, ScanLine} from 'lucide-react';
import {api} from '../../lib/api';
import {saveUser} from '../../lib/auth';
import {Button, ErrorMessage} from '../../components/common/UI';
import './login.css';

export default function Login() {
  const [role, setRole] = useState('user');
  const [citizenIntent, setCitizenIntent] = useState('login');
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [delivery, setDelivery] = useState(null);
  const [officerId, setOfficerId] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();

  async function sendOtp() {
    setLoading(true); setError('');
    try { setDelivery(await api.requestPhoneOtp(phone, citizenIntent)); }
    catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  async function verifyOtp() {
    setLoading(true); setError('');
    try {
      const result = await api.verifyPhoneOtp(phone, otp, citizenIntent);
      saveUser(result.user);
      router.push(result.profile_completed ? '/user' : '/user/profile');
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  async function officerLogin(event) {
    event.preventDefault(); setLoading(true); setError('');
    try {
      const result = await api.login({officer_id: officerId, password, role: 'officer'});
      saveUser(result.user);
      router.push('/officer');
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  function resetCitizenChallenge() {
    setDelivery(null);
    setOtp('');
    setError('');
  }

  function chooseCitizenIntent(intent) {
    setCitizenIntent(intent);
    resetCitizenChallenge();
  }

  return <main className="login-page cadastral-login">
    <section className="login-introduction" aria-label="BhumiAI introduction">
      <div className="login-branding"><div className="logo-line"><span className="logo-mark"><MapPinned size={22}/></span><b>Bhumi<span>AI</span></b></div><p className="initiative-line">LAND RECORD INTELLIGENCE</p></div>
      <div className="landing-story"><div className="eyebrow"><span/> TRUSTED RECORD MODERNIZATION</div><h1>Legacy land records,<br/><em>transformed</em> into trusted<br/>digital records.</h1><p>Digitization <i>•</i> Human verification <i>•</i> Traceability</p></div>
      <div className="record-journey" aria-label="Legacy document flows to structured record and human verified record"><div className="journey-step"><FileText size={18}/><span>Legacy document</span></div><ArrowRight className="journey-arrow" size={18}/><div className="journey-step"><ScanLine size={18}/><span>Structured record</span></div><ArrowRight className="journey-arrow" size={18}/><div className="journey-step verified"><CheckCircle2 size={18}/><span>Human verified</span></div></div>
      <div className="document-motif" aria-hidden="true"><span>KHATAUNI / RECORD EXTRACT</span><b/><i/><i/><i/><i/></div>
    </section>
    <section className="login-form-wrap">
      <div className="login-card">
        <div className="login-card-heading"><div className="eyebrow"><LockKeyhole size={13}/> SECURE WORKSPACE ACCESS</div><h1>{role === 'user' ? (citizenIntent === 'login' ? 'Log in to your workspace' : 'Register as a submitter') : 'Officer workspace access'}</h1><p>{role === 'user' ? (citizenIntent === 'login' ? 'Use the phone number registered to your citizen account.' : 'Create a citizen account using your Indian mobile number.') : 'Use credentials issued by the authorized government administrator.'}</p></div>
        <div className="login-field"><label>Workspace</label><select value={role} onChange={event => { setRole(event.target.value); resetCitizenChallenge(); }}><option value="user">Record Submitter</option><option value="officer">Verification Officer</option></select></div>
        {role === 'user' ? <>
          <div className="citizen-auth-tabs" role="group" aria-label="Citizen authentication choice"><button type="button" className={citizenIntent === 'login' ? 'active' : ''} aria-pressed={citizenIntent === 'login'} onClick={() => chooseCitizenIntent('login')}>Login</button><button type="button" className={citizenIntent === 'register' ? 'active' : ''} aria-pressed={citizenIntent === 'register'} onClick={() => chooseCitizenIntent('register')}>Register</button></div>
          <div className="login-field"><label>Indian mobile number</label><input value={phone} onChange={event => setPhone(event.target.value)} placeholder="9876543210 or +919876543210" inputMode="tel" disabled={Boolean(delivery)} required/></div>
          {delivery ? <>
            <p className="auth-context">Verification code for <b>{phone}</b>. {delivery.delivery === 'development' ? 'Development OTP generated — no SMS was sent.' : ''}</p>
            {delivery.development_otp && <p className="login-success">Development code: <b>{delivery.development_otp}</b></p>}
            <div className="login-field"><label>6-digit verification code</label><input value={otp} onChange={event => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" maxLength={6} placeholder="123456"/></div>
            <Button onClick={verifyOtp} loading={loading} loadingText="Checking code…" disabled={otp.length !== 6}>Verify & continue <ArrowRight size={17}/></Button>
            <button className="auth-context change-number" type="button" onClick={resetCitizenChallenge}>Change phone number</button>
          </> : <Button onClick={sendOtp} loading={loading} loadingText="Sending code…" disabled={!phone}>Send OTP <ArrowRight size={17}/></Button>}
        </> : <form onSubmit={officerLogin}>
          <div className="login-field"><label>Government Officer ID</label><input value={officerId} onChange={event => setOfficerId(event.target.value)} required/></div>
          <div className="login-field"><label>Issued Password</label><input type="password" value={password} onChange={event => setPassword(event.target.value)} required/></div>
          <Button loading={loading} loadingText="Signing in…">Access workspace <ArrowRight size={17}/></Button>
        </form>}
        <ErrorMessage>{error}</ErrorMessage>
      </div>
      <p className="login-assurance">Access is role-based and record actions remain traceable.</p>
    </section>
  </main>;
}
