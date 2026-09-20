export const getUser = () => { if (typeof window === 'undefined') return null; try { return JSON.parse(localStorage.getItem('landsight_user') || 'null'); } catch { return null; } };
export const saveUser = (user) => localStorage.setItem('landsight_user', JSON.stringify(user));
export const signOut = () => localStorage.removeItem('landsight_user');
