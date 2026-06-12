async function carregarConfigSensor() {
  const select = document.getElementById('sensorSelectControlo');
  const sensorId = select.value;
  if (!sensorId) return;

  const spinner     = document.getElementById('loadingSpinner');
  const statusBadge = document.getElementById('sensorStatus');

  spinner.style.display = 'block';
  statusBadge.innerHTML = '<span class="status-badge loading">A carregar...</span>';

  try {
    const res  = await fetch(`/api/parametros/${sensorId}`);
    const data = await res.json();

    if (data.success) {
      popularFormulario(data.config);
      const cacheInfo = data.cached ? ` (cache ${Math.round(data.cache_age_seconds)}s)` : ' (tempo real)';
      statusBadge.innerHTML = `<span class="status-badge online">Online${cacheInfo}</span>`;
    } else {
      statusBadge.innerHTML = '<span class="status-badge offline">Offline</span>';
      alert('Erro ao carregar configuração: ' + (data.erro || 'Desconhecido'));
    }
  } catch (err) {
    statusBadge.innerHTML = '<span class="status-badge offline">Erro</span>';
    alert('Erro ao comunicar com o servidor: ' + err.message);
  } finally {
    spinner.style.display = 'none';
  }
}

function popularFormulario(config) {
  const form = document.forms['configForm'];

  if (config.station) {
    form.sensor_ID.value    = config.station.sensor_ID    || '';
    form.local_Info.value   = config.station.local_Info   || '';
    form.tipo.value         = config.station.tipo         || '';
    form.local_Lat.value    = config.station.local_Lat    || '';
    form.local_Long.value   = config.station.local_Long   || '';
    form.local_Alt.value    = config.station.local_Alt    || '';
    form.Tipo.value         = config.station.Tipo         || '';
    form.Tipo2.value        = config.station.Tipo2        || '';
  }
  if (config.audio) {
    form.sample_rate.value         = config.audio.sample_rate         || '';
    form.channels.value            = config.audio.channels            || '';
    form.dtype.value               = config.audio.dtype               || '';
    form.chunk_size.value          = config.audio.chunk_size          || '';
    form.nbits.value               = config.audio.nbits               || '';
    form.dif_out_in_db.value       = config.audio.dif_out_in_db       || '';
    form.target_device_name.value  = config.audio.target_device_name  || '';
  }
  if (config.timing) {
    form.file_duration.value            = config.timing.file_duration            || '';
    form.session_duration.value         = config.timing.session_duration         || '';
    form.segment_duration.value         = config.timing.segment_duration         || '';
    form.percentil_duration_laxx.value  = config.timing.percentil_duration_laxx  || '';
    form.time_csv_store.value           = config.timing.time_csv_store           || '';
    form.file_duration_csv.value        = config.timing.file_duration_csv        || '';
  }
  if (config.audio_save) {
    form.file_prefix.value = config.audio_save.file_prefix || '';
    form.bitrate.value     = config.audio_save.bitrate     || '';
  }
  if (config.levels) {
    form.cal94.value            = config.levels.cal94            || '';
    form.pref.value             = config.levels.pref             || '';
    form.n_13octave_bands.value = config.levels.n_13octave_bands || '';
  }
  if (config.noise_reduction) {
    form.reduction_factor.value       = config.noise_reduction.reduction_factor       || '';
    form.initial_noise_frames.value   = config.noise_reduction.initial_noise_frames   || '';
  }
  if (config.percentil_noise) {
    form.percentil_value.value          = config.percentil_noise.percentil_value          || '';
    form.threshold_event_offset.value   = config.percentil_noise.threshold_event_offset   || '';
    form.percentil_LAxx.value           = config.percentil_noise.percentil_LAxx           || '';
  }
  if (config.leds_display) {
    form.level_led_green.value        = config.leds_display.level_led_green        || '';
    form.level_led_green_yellow.value = config.leds_display.level_led_green_yellow || '';
    form.level_led_yellow.value       = config.leds_display.level_led_yellow       || '';
    form.level_led_yellow_red.value   = config.leds_display.level_led_yellow_red   || '';
    form.gpio_green.value             = config.leds_display.gpio_green             || '';
    form.gpio_yellow.value            = config.leds_display.gpio_yellow            || '';
    form.gpio_red.value               = config.leds_display.gpio_red               || '';
  }
  if (config.mqtt) {
    form.broker.value = config.mqtt.broker || '';
    form.port.value   = config.mqtt.port   || '';
    form.topic.value  = config.mqtt.topic  || '';
  }
  if (config.sound_event_detect) {
    form.model_path.value       = config.sound_event_detect.model_path       || '';
    form.classes.value          = config.sound_event_detect.classes           || '';
    form.family_map.value       = config.sound_event_detect.family_map        || '';
    form.weight_map.value       = config.sound_event_detect.weight_map        || '';
    form.family_map2.value      = config.sound_event_detect.family_map2       || '';
    form.weight_map2.value      = config.sound_event_detect.weight_map2       || '';
    form.blacklist.value        = Array.isArray(config.sound_event_detect.blacklist)
      ? config.sound_event_detect.blacklist.join(', ') : '';
    form.size_event.value       = config.sound_event_detect.size_event        || '';
    form.reduce_Eventmusic.value= config.sound_event_detect.reduce_Eventmusic || '';
  }
  if (config.config_flags) {
    const flags = config.config_flags;
    const cb = name => { form[name].checked = flags[name] || false; };
    ['plots_ok','save_audiofile_ok','noise_timeline_ok','echo_short_ok','echo_complete_ok',
     'show_leds_display_ok','noise_reduction_ok','publica_mqtt_ok','plat_mac','sound_classification_ok']
      .forEach(cb);
  }
}

async function guardarConfiguracoes() {
  const form = document.forms['configForm'];
  const sensorId = form.sensor_name.value;
  if (!sensorId) { alert('Por favor selecione um sensor primeiro'); return; }

  const gc = name => form[name]?.checked || false;

  const config = {
    station: {
      sensor_ID: +form.sensor_ID.value, local_Info: form.local_Info.value,
      tipo: form.tipo.value, local_Lat: +form.local_Lat.value,
      local_Long: +form.local_Long.value, local_Alt: +form.local_Alt.value,
      Tipo: form.Tipo.value, Tipo2: form.Tipo2.value
    },
    audio: {
      sample_rate: +form.sample_rate.value, channels: +form.channels.value,
      dtype: form.dtype.value, chunk_size: +form.chunk_size.value,
      nbits: +form.nbits.value, dif_out_in_db: +form.dif_out_in_db.value,
      target_device_name: form.target_device_name.value
    },
    timing: {
      file_duration: +form.file_duration.value,
      session_duration: form.session_duration.value ? +form.session_duration.value : null,
      segment_duration: +form.segment_duration.value,
      percentil_duration_laxx: +form.percentil_duration_laxx.value,
      time_csv_store: +form.time_csv_store.value,
      file_duration_csv: +form.file_duration_csv.value
    },
    audio_save: { file_prefix: form.file_prefix.value, bitrate: +form.bitrate.value },
    levels: { cal94: +form.cal94.value, pref: +form.pref.value, n_13octave_bands: +form.n_13octave_bands.value },
    noise_reduction: {
      reduction_factor: +form.reduction_factor.value,
      initial_noise_frames: +form.initial_noise_frames.value
    },
    percentil_noise: {
      percentil_value: +form.percentil_value.value,
      threshold_event_offset: +form.threshold_event_offset.value,
      percentil_LAxx: +form.percentil_LAxx.value
    },
    leds_display: {
      level_led_green: +form.level_led_green.value,
      level_led_green_yellow: +form.level_led_green_yellow.value,
      level_led_yellow: +form.level_led_yellow.value,
      level_led_yellow_red: +form.level_led_yellow_red.value,
      gpio_green: +form.gpio_green.value, gpio_yellow: +form.gpio_yellow.value,
      gpio_red: +form.gpio_red.value
    },
    mqtt: { broker: form.broker.value, port: +form.port.value, topic: form.topic.value },
    config_flags: {
      plots_ok: gc('plots_ok'), save_audiofile_ok: gc('save_audiofile_ok'),
      noise_timeline_ok: gc('noise_timeline_ok'), echo_short_ok: gc('echo_short_ok'),
      echo_complete_ok: gc('echo_complete_ok'), show_leds_display_ok: gc('show_leds_display_ok'),
      noise_reduction_ok: gc('noise_reduction_ok'), publica_mqtt_ok: gc('publica_mqtt_ok'),
      plat_mac: gc('plat_mac'), sound_classification_ok: gc('sound_classification_ok')
    },
    sound_event_detect: {
      model_path: form.model_path.value, classes: form.classes.value,
      family_map: form.family_map.value, weight_map: form.weight_map.value,
      family_map2: form.family_map2.value, weight_map2: form.weight_map2.value,
      blacklist: form.blacklist.value.split(',').map(x => x.trim()).filter(x => x),
      size_event: +form.size_event.value, reduce_Eventmusic: +form.reduce_Eventmusic.value
    }
  };

  try {
    const res = await fetch('/api/parametros', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sensor_id: sensorId, config, checksum: null })
    });
    const response = await res.json();
    if (response.success) {
      const needsReboot = response.needs_reboot ? ' (Reinício necessário na estação)' : '';
      alert(`Parâmetros enviados com sucesso!${needsReboot}\n\nStatus: ${response.status}`);
    } else {
      alert('Erro ao enviar os parâmetros: ' + (response.erro || 'Desconhecido'));
    }
  } catch (err) {
    alert('Erro ao enviar os parâmetros: ' + err.message);
  }
}

async function guardarUrlGrafana() {
  const url = document.getElementById('grafana_url').value.trim();
  if (!url) { alert('URL não pode ser vazio.'); return; }
  try {
    const res = await fetch('/api/system_config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grafana_url: url })
    });
    const data = await res.json();
    if (res.ok) {
      alert('URL do Grafana guardado com sucesso!');
    } else {
      alert('Erro: ' + (data.erro || 'desconhecido'));
    }
  } catch (err) {
    alert('Erro ao guardar: ' + err.message);
  }
}

async function carregarSensoresControlo() {
  try {
    const res = await fetch('/api/sensores');
    const sensores = await res.json();
    const select = document.getElementById('sensorSelectControlo');
    select.innerHTML = '<option value="" disabled selected>-- Escolher sensor --</option>';
    sensores.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.replace(/\D/g, '');
      opt.textContent = s.charAt(0).toUpperCase() + s.slice(1);
      select.appendChild(opt);
    });
  } catch (err) {
    console.error('Erro ao carregar sensores:', err);
  }
}

function confirmarReboot() {
  const select = document.getElementById('sensorSelectControlo');
  if (!select.value) { alert('Seleciona um sensor primeiro.'); return; }
  document.getElementById('rebootSensorNome').textContent = select.options[select.selectedIndex].text;
  new bootstrap.Modal(document.getElementById('modalReboot')).show();
}

async function executarReboot() {
  const sensorId = document.getElementById('sensorSelectControlo').value;
  const btn      = document.getElementById('btnConfirmarReboot');
  btn.disabled   = true;
  btn.textContent = 'A enviar...';

  try {
    const res  = await fetch('/api/reboot', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ sensor_id: sensorId })
    });
    const data = await res.json();
    bootstrap.Modal.getInstance(document.getElementById('modalReboot')).hide();
    if (data.success) {
      alert('Comando de reboot enviado. A estação vai reiniciar em segundos.');
    } else {
      alert('Erro: ' + (data.erro || 'desconhecido'));
    }
  } catch (err) {
    alert('Erro ao enviar reboot: ' + err.message);
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Reiniciar';
  }
}

window.addEventListener('load', carregarSensoresControlo);
