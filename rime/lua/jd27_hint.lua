local function startswith(str, start)
    return string.sub(str, 1, string.len(start)) == start
end

local function hint(cand, input, env)
    -- 简码提示
    if utf8.len(cand.text) <= 1 then
        return 0
    end
    local reverse = env.reverse
    local s = env.s
    local b = env.b

    local lookup = " " .. reverse:lookup(cand.text) .. " "
    local sbb = string.match(lookup, " (["..s.."]["..b.."]+) ")
    local short = string.match(lookup, " (["..s.."]["..s.."]) ")
    
    if string.len(input) > 1 then
        if sbb and not startswith(sbb, input) then
            cand:get_genuine().comment = cand.comment .. "〔" .. sbb .. "〕"
            return 1
        end

        if short and not startswith(short, input) then
            cand:get_genuine().comment = cand.comment .. "〔" .. short .. "⛔️" .. "〕"
            return 2
        end
    end

    return 0
end

local function commit_hint(cand)
    -- 顶功提示
    cand:get_genuine().comment = '⛔️' .. cand.comment
end

local function filter(input, env)
    local context = env.engine.context
    local is_hint_on = context:get_option('sbb_hint')
    local is_completion_on = context:get_option('completion')
    local input_text = context.input
    local no_commit = string.len(input_text) < 4 and string.match(input_text, "^["..env.s.."]+$")
    local has_table = false
    local first = true

    for cand in input:iter() do
        if no_commit and first then
            commit_hint(cand)
        end
        first = false
        if cand.type == 'table' then
            if is_hint_on then
                hint(cand, input_text, env)
            end

            yield(cand)
            has_table = true
        elseif cand.type == 'completion' then
            if is_completion_on then
                yield(cand)
            elseif not has_table then
                yield(cand)
                return
            else
                return
            end
        else
            yield(cand)
        end
    end
end

local function init(env)
    local config = env.engine.schema.config
    local dict_name = config:get_string("translator/dictionary")

    env.b = config:get_string("topup/topup_with")
    env.s = config:get_string("topup/topup_this")
    env.reverse = ReverseDb("build/".. dict_name .. ".reverse.bin")
end

return { init = init, func = filter }