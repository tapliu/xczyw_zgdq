const MusicManager = {
  _audio: new Audio(),
  _scene: null,
  _enabled: true,
  _volume: 0.4,
  _battleIndex: -1,

  _tracks: {
    menu: { src: '/music/bgm_menu_01.m4a', loop: true },
    draw: { src: '/music/bgm_menu_02.m4a', loop: true },
    place: { src: '/music/bgm_place_01.m4a', loop: true },
    battle: [
      { src: '/music/bgm_battle_01.m4a' },
      { src: '/music/bgm_battle_02.m4a' },
      { src: '/music/bgm_battle_03.m4a' },
      { src: '/music/bgm_battle_04.m4a' },
      { src: '/music/bgm_battle_05.m4a' },
      { src: '/music/bgm_battle_06.m4a' },
    ],
    victory: { src: '/music/bgm_battle_04.m4a', loop: false },
    defeat: { src: '/music/bgm_menu_02.m4a', loop: false },
  },

  _nextBattle() {
    const list = this._tracks.battle;
    let idx;
    do {
      idx = Math.floor(Math.random() * list.length);
    } while (idx === this._battleIndex && list.length > 1);
    this._battleIndex = idx;
    return list[idx];
  },

  play(scene) {
    if (scene === this._scene && !this._audio.paused) return;
    this._scene = scene;
    if (!this._enabled) { this.stop(); return; }

    const track = scene === 'battle' ? this._nextBattle() : this._tracks[scene];
    if (!track) return;

    this._audio.loop = track.loop !== false;
    this._audio.volume = this._volume;
    if (this._audio.src !== track.src) {
      this._audio.src = track.src;
      this._audio.play().catch(e => console.warn('Music play error:', e));
    } else if (this._audio.paused) {
      this._audio.play().catch(e => console.warn('Music resume error:', e));
    }
  },

  _onEnded() {
    if (this._scene === 'battle') this.play('battle');
  },

  stop() {
    this._audio.pause();
    this._audio.src = '';
    this._battleIndex = -1;
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
      this.stop();
    }
    return this._enabled;
  },

  isEnabled() { return this._enabled; },
  getVolume() { return this._volume; },
};

MusicManager._audio.addEventListener('ended', () => MusicManager._onEnded());
