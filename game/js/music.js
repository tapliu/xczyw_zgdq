const MusicManager = {
  _audio: new Audio(),
  _scene: null,
  _enabled: true,
  _volume: 0.4,
  _battleIndex: -1,

  _tracks: {
    ambient: [
      { src: '/music/bgm_menu_01.m4a' },
      { src: '/music/bgm_menu_02.m4a' },
      { src: '/music/bgm_place_01.m4a' },
    ],
    battle: [
      { src: '/music/bgm_battle_01.m4a' },
      { src: '/music/bgm_battle_02.m4a' },
      { src: '/music/bgm_battle_03.m4a' },
      { src: '/music/bgm_battle_04.m4a' },
      { src: '/music/bgm_battle_05.m4a' },
      { src: '/music/bgm_battle_06.m4a' },
    ],
    victory: { src: '/music/bgm_battle_04.m4a' },
    defeat: { src: '/music/bgm_menu_02.m4a' },
  },
  _ambientIndex: -1,
  _battleIndex: -1,

  _nextIndex(list, currentIndex) {
    if (!list.length) return -1;
    let idx;
    do {
      idx = Math.floor(Math.random() * list.length);
    } while (idx === currentIndex && list.length > 1);
    return idx;
  },

  play(scene) {
    if (scene === this._scene && !this._audio.paused) return;
    this._scene = scene;
    if (!this._enabled) { return; }

    let track;
    if (scene === 'battle') {
      const idx = this._nextIndex(this._tracks.battle, this._battleIndex);
      this._battleIndex = idx;
      track = this._tracks.battle[idx];
    } else if (scene === 'victory' || scene === 'defeat') {
      track = this._tracks[scene];
    } else {
      // menu / draw / place - ambient rotation
      const idx = this._nextIndex(this._tracks.ambient, this._ambientIndex);
      this._ambientIndex = idx;
      track = this._tracks.ambient[idx];
    }
    if (!track) return;

    this._audio.loop = false;
    this._audio.volume = this._volume;
    const absSrc = track.src.startsWith('/') ? new URL(track.src, location.origin).href : track.src;
    if (this._audio.src !== absSrc) {
      this._audio.src = absSrc;
      this._audio.play().catch(e => console.warn('Music play error:', e));
    } else if (this._audio.paused) {
      this._audio.play().catch(e => console.warn('Music resume error:', e));
    }
  },

  next() {
    if (this._scene === 'victory' || this._scene === 'defeat') return;
    const isBattle = this._scene === 'battle';
    const list = isBattle ? this._tracks.battle : this._tracks.ambient;
    if (!list.length) return;
    let idx;
    do {
      idx = Math.floor(Math.random() * list.length);
    } while (idx === (isBattle ? this._battleIndex : this._ambientIndex) && list.length > 1);
    if (isBattle) this._battleIndex = idx;
    else this._ambientIndex = idx;
    const track = list[idx];
    if (!track) return;
    this._audio.src = track.src.startsWith('/') ? new URL(track.src, location.origin).href : track.src;
    this._audio.play().catch(e => console.warn('Music play error:', e));
  },

  stop() {
    this._audio.pause();
    this._audio.currentTime = 0;
    this._battleIndex = -1;
    this._ambientIndex = -1;
  },

  setVolume(v) {
    this._volume = Math.max(0, Math.min(1, v));
    this._audio.volume = this._volume;
  },

  toggle() {
    this._enabled = !this._enabled;
    if (this._enabled) {
      if (this._scene) this.play(this._scene);
    } else {
      this._audio.pause();
    }
    return this._enabled;
  },

  isEnabled() { return this._enabled; },
  getVolume() { return this._volume; },

  _onEnded() {
    if (this._scene === 'battle') this.play('battle');
    else if (this._scene !== 'victory' && this._scene !== 'defeat') this.play(this._scene);
  },
};

MusicManager._audio.addEventListener('ended', () => MusicManager._onEnded());
MusicManager._audio.preload = 'auto';
