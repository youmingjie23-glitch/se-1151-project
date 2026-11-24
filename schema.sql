CREATE TABLE IF NOT EXISTS users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username varchar(50) NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role text NOT NULL DEFAULT 'user' CONSTRAINT users_role_check CHECK (role IN ('user', 'teacher', 'admin')),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz,
    reviewed_by bigint REFERENCES users (id)
);

-- Replace the original users_role_check on previously initialized databases.
ALTER TABLE users
    DROP CONSTRAINT IF EXISTS users_role_check,
    ADD CONSTRAINT users_role_check CHECK (role IN ('user', 'teacher', 'admin'));

CREATE TABLE IF NOT EXISTS rooms (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code varchar(50) NOT NULL UNIQUE,
    name varchar(100) NOT NULL,
    capacity integer CHECK (capacity > 0)
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash bytea PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '8 hours')
);

CREATE INDEX IF NOT EXISTS auth_sessions_expires_at_idx ON auth_sessions (expires_at);

CREATE TABLE IF NOT EXISTS official_courses (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    academic_year integer NOT NULL,
    semester smallint NOT NULL,
    department text NOT NULL,
    course_code text NOT NULL,
    section text NOT NULL,
    title text NOT NULL,
    raw_teachers text NOT NULL,
    raw_time_code text NOT NULL,
    raw_classrooms text NOT NULL,
    UNIQUE (academic_year, semester, department, course_code, section)
);

CREATE TABLE IF NOT EXISTS course_schedules (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    official_course_id bigint REFERENCES official_courses (id),
    title text NOT NULL,
    teacher_id bigint NOT NULL REFERENCES users (id),
    -- Dates and times use local time in Taiwan (Asia/Taipei).
    class_date date NOT NULL,
    start_time time NOT NULL,
    end_time time NOT NULL,
    preferred_room_id bigint REFERENCES rooms (id),
    CHECK (end_time > start_time)
);
