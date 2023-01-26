function z = lead(x,n,v)

switch(nargin)
    
    case 1
        z = flipud(lag(flipud(x)));       
    case 2
        z = flipud(lag(flipud(x),n));       
    case 3
        z = flipud(lag(flipud(x),n,v));       
    otherwise
        error('lag: wrong # of input arguments');
end;
