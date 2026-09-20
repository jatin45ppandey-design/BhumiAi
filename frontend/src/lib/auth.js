// Identity is established only by the HttpOnly server session. This memory
// cache is for display convenience and is never authorization proof.
let currentUser = null;
export const getUser = () => currentUser;
export const saveUser = (user) => { currentUser = user || null; };
export const signOut = () => { currentUser = null; };
