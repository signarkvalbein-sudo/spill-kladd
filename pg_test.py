import pygame
import random
import math

pygame.init()

screen = pygame.display.set_mode((800, 600))
pygame.display.set_caption("Pygame Test")
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 24)

ARC_HALF_ANGLE = 36
BLOCK_RADIUS = 50
ATTACK_RADIUS = 90
ATTACK_DURATION = 10
ATTACK_COOLDOWN = 25

JUMP_EFFECT_PATH = "Sprites/effects/jump_effect.png" 
JUMP_EFFECT_COLS = 2
JUMP_EFFECT_ROWS = 5
JUMP_EFFECT_FRAME_COUNT = 9          # 10 cells in the grid, only 9 are used
JUMP_EFFECT_FRAME_DURATION = 3       # game frames each animation frame is shown


def load_jump_effect_frames(target_size):
    """Slices the spritesheet into JUMP_EFFECT_FRAME_COUNT frames (row-major:
    left-to-right, then top-to-bottom) and scales each to target_size."""
    sheet = pygame.image.load(JUMP_EFFECT_PATH).convert_alpha()
    sheet_w, sheet_h = sheet.get_size()
    frame_w = sheet_w // JUMP_EFFECT_COLS
    frame_h = sheet_h // JUMP_EFFECT_ROWS

    frames = []
    for i in range(JUMP_EFFECT_FRAME_COUNT):
        col = i % JUMP_EFFECT_COLS
        row = i // JUMP_EFFECT_COLS
        frame = sheet.subsurface(pygame.Rect(col * frame_w, row * frame_h, frame_w, frame_h))
        frame = pygame.transform.smoothscale(frame, target_size)
        frames.append(frame)
    return frames


def angle_diff(a, b):
    d = (a - b) % 360
    if d > 180:
        d -= 360
    return d


class Particle:
    def __init__(self, x, y, color=(150, 220, 255)):
        self.x = x
        self.y = y
        angle = random.uniform(0, 360)
        speed = random.uniform(2, 5)
        self.vx = speed * pygame.math.Vector2(1, 0).rotate(angle).x
        self.vy = speed * pygame.math.Vector2(1, 0).rotate(angle).y
        self.radius = random.uniform(3, 6)
        self.lifetime = 20
        self.age = 0
        self.color = color

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.2
        self.age += 1

    def draw(self, surface):
        if self.age < self.lifetime:
            alpha = max(0, 255 - int((self.age / self.lifetime) * 255))
            size = max(0, self.radius - (self.age / self.lifetime) * self.radius)
            particle_surf = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(particle_surf, (*self.color, alpha), (self.radius, self.radius), size)
            surface.blit(particle_surf, (self.x - self.radius, self.y - self.radius))

    def is_dead(self):
        return self.age >= self.lifetime


class Player(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = pygame.Surface((50, 50))
        self.image.fill((0, 200, 255))
        self.rect = self.image.get_rect()
        self.rect.topleft = (x, y)
        self.speed = 5

        self.velocity_y = 0
        self.gravity = 0.8
        self.jump_strength = -15
        self.bounce_strength = -24  # noticeably higher than a normal jump
        self.on_ground = False

        self.jump_count = 0
        self.max_jumps = 2

        self.particles = []
        effect_size = (self.rect.width * 8, self.rect.height * 1)  
        self.jump_effect_frames = load_jump_effect_frames(effect_size)
        self.jump_effect_index = 0
        self.jump_effect_timer = 0
        self.jump_effect_playing = False

        self.aim_angle = 0
        self.blocking = False
        self.attacking = False
        self.attack_timer = 0
        self.attack_cooldown_timer = 0
        self.has_hit_this_attack = False

        self.health = 100

    def move(self, dx, dy, obstacles):
        self.rect.x += dx
        self.check_collision(dx, 0, obstacles)

        self.velocity_y += self.gravity
        self.check_block_collision(obstacles)  # may bounce or halt the fall before it happens
        self.rect.y += self.velocity_y
        self.on_ground = False
        self.check_collision(0, self.velocity_y, obstacles)

        for particle in self.particles:
            particle.update()
        self.particles = [p for p in self.particles if not p.is_dead()]

        self.update_jump_effect()

    def jump(self):
        if self.jump_count < self.max_jumps:
            self.velocity_y = self.jump_strength
            self.jump_count += 1
            if self.jump_count == 2:
                self.spawn_splash()

    def spawn_splash(self):
        self.jump_effect_playing = True
        self.jump_effect_index = 0
        self.jump_effect_timer = 0

    def spawn_bounce_splash(self):
        spawn_x = self.rect.centerx
        spawn_y = self.rect.bottom
        for _ in range(18):
            self.particles.append(Particle(spawn_x, spawn_y, color=(255, 220, 100)))

    def update_jump_effect(self):
        if self.jump_effect_playing:
            self.jump_effect_timer += 1
            if self.jump_effect_timer >= JUMP_EFFECT_FRAME_DURATION:
                self.jump_effect_timer = 0
                self.jump_effect_index += 1
                if self.jump_effect_index >= len(self.jump_effect_frames):
                    self.jump_effect_playing = False
                    self.jump_effect_index = 0

    def update_aim(self, mouse_pos):
        dx = mouse_pos[0] - self.rect.centerx
        dy = mouse_pos[1] - self.rect.centery
        self.aim_angle = math.degrees(math.atan2(dy, dx))

    def start_block(self):
        if not self.attacking:
            self.blocking = True

    def stop_block(self):
        self.blocking = False

    def start_attack(self):
        if not self.blocking and self.attack_cooldown_timer <= 0 and not self.attacking:
            self.attacking = True
            self.attack_timer = ATTACK_DURATION
            self.attack_cooldown_timer = ATTACK_COOLDOWN
            self.has_hit_this_attack = False

    def update_combat(self):
        if self.attack_cooldown_timer > 0:
            self.attack_cooldown_timer -= 1

        if self.attacking:
            self.attack_timer -= 1
            if self.attack_timer <= 0:
                self.attacking = False

    def arc_hits(self, target_rect):
        """Kept for when you add your own enemies back in: checks if target_rect
        falls within the current attack arc (uses ATTACK_RADIUS)."""
        ex, ey = target_rect.center
        dx = ex - self.rect.centerx
        dy = ey - self.rect.centery
        dist = math.hypot(dx, dy)
        if dist > ATTACK_RADIUS + max(target_rect.width, target_rect.height) / 2:
            return False
        angle_to_target = math.degrees(math.atan2(dy, dx))
        return abs(angle_diff(angle_to_target, self.aim_angle)) <= ARC_HALF_ANGLE

    def is_blocking_angle(self, incoming_angle):
        return self.blocking and abs(angle_diff(incoming_angle, self.aim_angle)) <= ARC_HALF_ANGLE

    def check_block_collision(self, obstacles):
        """While blocking, check if the shield itself (out to BLOCK_RADIUS, across its
        72-degree arc) is touching an obstacle - independent of whether the player's
        body rect has reached it yet."""
        if not self.blocking or self.velocity_y <= 0:
            return

        cx, cy = self.rect.center
        steps = 10
        touching = None
        for i in range(steps + 1):
            a = math.radians(self.aim_angle - ARC_HALF_ANGLE + (2 * ARC_HALF_ANGLE) * (i / steps))
            px = cx + math.cos(a) * BLOCK_RADIUS
            py = cy + math.sin(a) * BLOCK_RADIUS
            for obstacle in obstacles:
                if obstacle.rect.collidepoint(px, py):
                    touching = obstacle
                    break
            if touching:
                break

        if touching:
            if self.is_blocking_angle(90):  # shield's arc covers straight-down
                self.velocity_y = self.bounce_strength
                self.on_ground = False
                self.jump_count = 0
                self.spawn_bounce_splash()
            else:
                self.velocity_y = 0

    def check_collision(self, dx, dy, obstacles):
        for obstacle in obstacles:
            if self.rect.colliderect(obstacle.rect):
                if dx > 0:
                    self.rect.right = obstacle.rect.left
                if dx < 0:
                    self.rect.left = obstacle.rect.right
                if dy > 0:
                    self.rect.bottom = obstacle.rect.top
                    self.velocity_y = 0
                    self.on_ground = True
                    self.jump_count = 0
                if dy < 0:
                    self.rect.top = obstacle.rect.bottom
                    self.velocity_y = 0

    def draw(self, surface):
        surface.blit(self.image, self.rect)
        for particle in self.particles:
            particle.draw(surface)
        if self.jump_effect_playing:
            frame = self.jump_effect_frames[self.jump_effect_index]
            frame_rect = frame.get_rect(midtop=self.rect.midbottom)
            surface.blit(frame, frame_rect)
        self.draw_arc_indicators(surface)

    def draw_arc_indicators(self, surface):
        cx, cy = self.rect.center
        if self.blocking:
            self.draw_block_arc(surface, cx, cy)
        elif self.attacking:
            self.draw_attack_slash(surface, cx, cy)
        else:
            self.draw_idle_dot(surface, cx, cy)

    def draw_idle_dot(self, surface, cx, cy):
        rad = math.radians(self.aim_angle)
        dot_x = cx + math.cos(rad) * ATTACK_RADIUS
        dot_y = cy + math.sin(rad) * ATTACK_RADIUS
        pygame.draw.circle(surface, (255, 255, 255), (int(dot_x), int(dot_y)), 4)

    def draw_block_arc(self, surface, cx, cy):
        start_angle = self.aim_angle - ARC_HALF_ANGLE
        end_angle = self.aim_angle + ARC_HALF_ANGLE
        points = []
        steps = 20
        for i in range(steps + 1):
            a = math.radians(start_angle + (end_angle - start_angle) * (i / steps))
            points.append((cx + math.cos(a) * BLOCK_RADIUS, cy + math.sin(a) * BLOCK_RADIUS))
        pygame.draw.lines(surface, (255, 255, 255), False, points, 4)

    def draw_attack_slash(self, surface, cx, cy):
        progress = 1 - (self.attack_timer / ATTACK_DURATION)
        start_angle = self.aim_angle - ARC_HALF_ANGLE
        end_angle = self.aim_angle + ARC_HALF_ANGLE
        sweep_end = start_angle + (end_angle - start_angle) * min(1.0, progress * 1.5)

        steps = 20
        points = []
        inner_points = []
        for i in range(steps + 1):
            t = i / steps
            a = math.radians(start_angle + (sweep_end - start_angle) * t)
            points.append((cx + math.cos(a) * ATTACK_RADIUS, cy + math.sin(a) * ATTACK_RADIUS))
            inner_points.append((cx + math.cos(a) * ATTACK_RADIUS * 0.85, cy + math.sin(a) * ATTACK_RADIUS * 0.85))

        if len(points) > 1:
            pygame.draw.lines(surface, (255, 255, 255), False, points, 6)
            pygame.draw.lines(surface, (120, 200, 255), False, inner_points, 3)


class Obstacle(pygame.sprite.Sprite):
    def __init__(self, x, y, width=40, height=40):
        super().__init__()
        self.image = pygame.Surface((width, height))
        self.image.fill((255, 100, 100))
        self.rect = self.image.get_rect()
        self.rect.topleft = (x, y)


ground = Obstacle(0, 550, 800, 50)
player = Player(100, 100)
obstacle = Obstacle(300, 300)

all_sprites = pygame.sprite.Group()
all_sprites.add(obstacle, ground)
obstacles = pygame.sprite.Group()
obstacles.add(obstacle)
obstacles.add(ground)

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                player.jump()
            if event.key == pygame.K_LSHIFT:
                player.start_block()
            if event.key == pygame.K_w:
                player.start_attack()
        if event.type == pygame.KEYUP:
            if event.key == pygame.K_LSHIFT:
                player.stop_block()
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                player.start_attack()

    keys = pygame.key.get_pressed()
    dx = 0
    if keys[pygame.K_a]:
        dx = -player.speed
    if keys[pygame.K_d]:
        dx = player.speed

    player.update_aim(pygame.mouse.get_pos())
    player.move(dx, 0, obstacles)
    player.update_combat()

    screen.fill((0, 0, 0))
    all_sprites.draw(screen)
    player.draw(screen)

    hp_text = font.render(f"Player HP: {player.health}", True, (255, 255, 255))
    screen.blit(hp_text, (10, 10))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()